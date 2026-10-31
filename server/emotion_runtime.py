"""CPU adapters for pinned upstream models; checkpoints are loaded with weights_only."""
from functools import lru_cache
from pathlib import Path
import hashlib
import importlib.util
import json
import math
import os
import sys
import types

ROOT=Path(__file__).resolve().parents[1]


def available(engine):
    folders={'emo':'emo-disentanger','midi-emotion':'midi-emotion'}
    if engine not in folders:return False
    if importlib.util.find_spec('torch') is None or engine=='emo' and importlib.util.find_spec('transformers') is None:return False
    directory=ROOT/'models'/folders[engine]
    try:
        manifest=json.loads((ROOT/'models/emotion-models-manifest.json').read_text(encoding='utf-8'))
        files=[(ROOT/name,entry) for name,entry in manifest['files'].items() if name.startswith(f'models/{folders[engine]}/') or engine=='emo' and name.startswith('server/data/emo-stage')]
        return bool(files) and all(path.is_file() and path.stat().st_size==entry['bytes'] for path,entry in files) and (ROOT/'vendor'/folders[engine]/'SOURCE.json').is_file()
    except (OSError,ValueError,KeyError):return False


def verify(engine):
    folder='emo-disentanger' if engine=='emo' else 'midi-emotion'
    if not available(engine):raise ValueError(f'{engine} resources are missing. Prepare the downloaded emotion models first.')
    manifest=json.loads((ROOT/'models/emotion-models-manifest.json').read_text(encoding='utf-8'))
    selected={name:entry for name,entry in manifest['files'].items() if name.startswith(f'models/{folder}/') or engine=='emo' and name.startswith('server/data/emo-stage')}
    for name,entry in selected.items():
        path=ROOT/name
        with path.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
        if path.stat().st_size!=entry['bytes'] or sha!=entry['sha256']:raise ValueError(f'Emotion model resource is damaged: {name}')
    provenance=json.loads((ROOT/'vendor'/folder/'SOURCE.json').read_text(encoding='utf-8'))
    for name,sha in provenance['files'].items():
        if hashlib.sha256((ROOT/'vendor'/folder/name).read_bytes()).hexdigest()!=sha:raise ValueError('Emotion model source checksum mismatch.')
    return {'version':engine+'-cpu-v1','commit':provenance['commit'],'files':{name:entry['sha256'] for name,entry in selected.items()}}


def module(name,path,package=False):
    if name in sys.modules:return sys.modules[name]
    if package:
        result=types.ModuleType(name);result.__path__=[str(path)];sys.modules[name]=result;return result
    spec=importlib.util.spec_from_file_location(name,path);result=importlib.util.module_from_spec(spec);sys.modules[name]=result;spec.loader.exec_module(result);return result


@lru_cache(maxsize=1)
def midi_model():
    import torch
    provenance=verify('midi-emotion');torch.set_num_threads(4)
    path=ROOT/'models/midi-emotion/continuous_concat'
    config=torch.load(path/'model_config.pt',map_location='cpu',weights_only=True)
    maps=torch.load(path/'mappings.pt',map_location='cpu',weights_only=True)
    source=module('_local_audio_midi_emotion',ROOT/'vendor/midi-emotion/src/models/music_multi.py')
    model=source.MusicTransformerMulti(embedding_dim=config['d_model'],d_inner=config['d_inner'],d_condition=config['d_condition'],vocab_size=config['vocab_size'],num_layer=config['n_layer'],num_head=config['n_head'],max_seq=2048,dropout=config['dropout'],pad_token=0)
    model.load_state_dict(torch.load(path/'model.pt',map_location='cpu',weights_only=True,mmap=True),strict=True)
    model.eval();model.requires_grad_(False)
    return model,maps,provenance


@lru_cache(maxsize=1)
def emo_models():
    os.environ['USE_TF']='0';os.environ['USE_FLAX']='0'
    import torch
    provenance=verify('emo');torch.set_num_threads(4)
    base=ROOT/'vendor/emo-disentanger'
    module('_local_audio_emo1',base/'stage1_compose/model',True)
    first_module=module('_local_audio_emo1.plain_transformer',base/'stage1_compose/model/plain_transformer.py')
    first=first_module.PlainTransformer(512,216,12,8,512,2048,512,512,dec_dropout=.1,pre_lnorm=True)
    weights=ROOT/'models/emo-disentanger/best_weight/Functional-two'
    first.load_state_dict(torch.load(weights/'emopia_lead_sheet_finetune/ep016_loss0.685_params.pt',map_location='cpu',weights_only=True,mmap=True),strict=True)
    module('_local_audio_emo2',base/'stage2_accompaniment/model',True)
    second_module=module('_local_audio_emo2.music_gpt2',base/'stage2_accompaniment/model/music_gpt2.py')
    from transformers.models.gpt2.modeling_gpt2 import GPT2Block
    class CompatibleBlock(GPT2Block):
        def __init__(self,config,layer_idx=None):
            config._attn_implementation='eager';super().__init__(config,layer_idx)
        def forward(self,*args,**kwargs):
            hidden=args[0]
            if kwargs.get('attention_mask') is None:
                cache=kwargs.get('past_key_values');past=cache.get_seq_length(self.attn.layer_idx) if cache is not None else 0
                length=hidden.shape[-2]
                allowed=torch.arange(past+length)[None,:]<=past+torch.arange(length)[:,None]
                kwargs['attention_mask']=torch.zeros((1,1,length,past+length),dtype=hidden.dtype).masked_fill(~allowed,float('-inf'))
            output=super().forward(*args,**kwargs)
            return output if isinstance(output,tuple) else (output,)
    second_module.GPT2Block=CompatibleBlock
    second=second_module.MusicGPT2(329,12,8,512,2048,512,use_segment_emb=True,n_segment_types=2)
    state=torch.load(weights/'emopia_acccompaniment_finetune_gpt2/ep300_loss0.120_params.pt',map_location='cpu',weights_only=True,mmap=True)
    # Older transformers persisted deterministic causal-mask buffers. New versions
    # rebuild them; remove only these known non-learned keys, then load strictly.
    state={k:v for k,v in state.items() if not k.endswith(('.attn.bias','.attn.masked_bias'))}
    second.load_state_dict(state,strict=True)
    vocab=[json.loads((ROOT/f'server/data/emo-stage{i}-vocabulary.json').read_text(encoding='utf-8')) for i in (1,2)]
    for model in (first,second):model.eval();model.requires_grad_(False)
    return first,second,vocab,provenance


class MidiLogits:
    """Exact causal incremental forward for the upstream relative-attention model."""
    def __init__(self,model):self.model=model;self.tokens=[];self.condition=None;self.keys=[];self.values=[];self.last=None
    def __call__(self,tokens,condition):
        import torch
        condition=tuple(condition)
        append=self.condition==condition and tokens[:len(self.tokens)]==self.tokens and len(tokens)>len(self.tokens)
        if self.condition==condition and tokens==self.tokens:return self.last.clone()
        with torch.inference_mode():
            if not append:
                self.keys=[];self.values=[]
                x=torch.tensor([tokens]);mask=self.model.pad_token==x
                emb=self.model.embedding(x)*math.sqrt(self.model.embedding_dim-self.model.d_condition)
                cond=self.model.fc_condition(torch.tensor([condition],dtype=torch.float32)).unsqueeze(1).expand(-1,len(tokens),-1)
                hidden=self.model.dropout(self.model.pos_encoding(torch.cat([emb,cond],-1)))
                causal=torch.triu(torch.ones(len(tokens),len(tokens),dtype=torch.bool),diagonal=1)[None]|mask[:,None,:]
                for layer in self.model.enc_layers:
                    a=layer.rga;k=a.Wk(hidden).reshape(1,len(tokens),a.h,a.dh).permute(0,2,1,3);v=a.Wv(hidden).reshape(1,len(tokens),a.h,a.dh).permute(0,2,1,3)
                    self.keys.append(k);self.values.append(v);hidden=layer(hidden,causal)
                self.last=self.model.fc(hidden[:,-1])[0]
            else:
                for position in range(len(self.tokens),len(tokens)):
                    emb=self.model.embedding(torch.tensor([[tokens[position]]]))*math.sqrt(self.model.embedding_dim-self.model.d_condition)
                    cond=self.model.fc_condition(torch.tensor([condition],dtype=torch.float32)).unsqueeze(1)
                    hidden=torch.cat([emb,cond],-1)+self.model.pos_encoding.positional_embedding[:,position:position+1]
                    for i,layer in enumerate(self.model.enc_layers):
                        a=layer.rga;q=a.Wq(hidden).reshape(1,1,a.h,a.dh).permute(0,2,1,3)
                        k=a.Wk(hidden).reshape(1,1,a.h,a.dh).permute(0,2,1,3);v=a.Wv(hidden).reshape(1,1,a.h,a.dh).permute(0,2,1,3)
                        self.keys[i]=torch.cat([self.keys[i],k],2);self.values[i]=torch.cat([self.values[i],v],2)
                        length=self.keys[i].shape[2];relative=torch.einsum('bhld,md->bhlm',q,a.E[-length:])
                        logits=(q@self.keys[i].transpose(-1,-2)+relative)/math.sqrt(a.dh)
                        out=(logits.softmax(-1)@self.values[i]).permute(0,2,1,3).reshape(1,1,a.d)
                        hidden=layer.layernorm1(hidden+a.fc(out));hidden=layer.layernorm2(hidden+layer.FFN_suf(torch.relu(layer.FFN_pre(hidden))))
                    self.last=self.model.fc(hidden)[0,-1]
            self.tokens=tokens.copy();self.condition=condition
        return self.last.clone()


class EmoLeadLogits:
    def __init__(self,model):self.model=model;self.tokens=[];self.mems=tuple();self.last=None
    def __call__(self,tokens):
        import torch
        append=tokens[:len(self.tokens)]==self.tokens and len(tokens)>len(self.tokens)
        if tokens==self.tokens:return self.last.clone()
        new=tokens[len(self.tokens):] if append else tokens
        if not append:self.mems=tuple()
        with torch.inference_mode():self.last,self.mems=self.model.generate(torch.tensor([new]).t(),self.mems)
        self.tokens=tokens.copy();return self.last.clone()


class EmoPerformanceLogits:
    def __init__(self,model):self.model=model;self.tokens=[];self.segments=[];self.cache=None;self.last=None
    def __call__(self,tokens,segments):
        import torch
        from transformers.cache_utils import DynamicCache
        append=self.cache is not None and tokens[:len(self.tokens)]==self.tokens and segments[:len(self.segments)]==self.segments and len(tokens)>len(self.tokens)
        if self.cache is not None and tokens==self.tokens and segments==self.segments:return self.last.clone()
        position=len(self.tokens) if append else 0
        if not append:self.cache=DynamicCache(config=self.model.transformer_decoder[0].attn.config)
        with torch.inference_mode():
            hidden=self.model.token_emb(torch.tensor([tokens[position:]]))+self.model.segemb(torch.tensor([segments[position:]]))
            hidden=hidden+self.model.pe.pe[position:len(tokens)].permute(1,0,2)
            for block in self.model.transformer_decoder:hidden=block(hidden,past_key_values=self.cache,use_cache=True)[0]
            self.last=self.model.dec_out_proj(hidden[:,-1])[0]
        self.tokens=tokens.copy();self.segments=segments.copy();return self.last.clone()
