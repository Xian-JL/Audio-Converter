export const PAGE_WIDTH=840;
export function songTitle(name?:string){return (name||'Score').replace(/\.(mp3|flac)$/i,'').replace(/^.*?\s+-\s+/,'').replace(/^[《]|[》]$/g,'').trim()||'Score';}
export function pageFileName(title:string,page:number){return `《${title.replace(/[<>:"/\\|?*\x00-\x1f]/g,'_').slice(0,120)}》Page_${page}.png`;}
export function saveBlob(blob:Blob,name:string){const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),2000);}
/** Export clean engraving only; interactive hitboxes/highlighting never enter PNGs. */
export async function pagePng(source:SVGSVGElement,title:string,subtitle:string,page:number,total:number,instrumentation?:[string,string]):Promise<Uint8Array<ArrayBuffer>>{
  const svg=source.cloneNode(true) as SVGSVGElement;
  svg.querySelectorAll('.measure-hit-layer,.score-hitbox').forEach(n=>n.remove());
  svg.querySelectorAll('[tabindex]').forEach(n=>{n.removeAttribute('tabindex');n.removeAttribute('role');n.removeAttribute('aria-label');});
  svg.setAttribute('xmlns','http://www.w3.org/2000/svg');
  const width=parseFloat(svg.getAttribute('width')||'')||PAGE_WIDTH,height=parseFloat(svg.getAttribute('height')||'')||width*297/210;
  if(!svg.hasAttribute('viewBox'))svg.setAttribute('viewBox',`0 0 ${width} ${height}`);svg.setAttribute('width',String(width));svg.setAttribute('height',String(height));
  const url=URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(svg)],{type:'image/svg+xml'}));
  try{
    const image=new Image();image.src=url;await image.decode();
    const canvas=document.createElement('canvas');canvas.width=2480;canvas.height=3508;const ctx=canvas.getContext('2d');if(!ctx)throw Error('Image export unavailable');
    ctx.fillStyle='#fff';ctx.fillRect(0,0,2480,3508);ctx.fillStyle='#1b2420';ctx.textAlign='center';ctx.font='500 46px "Segoe UI", "Microsoft YaHei", sans-serif';
    // Avoid clipping very long uploaded titles while retaining the complete filename.
    ctx.fillText(title,1240,90,2240);ctx.font='26px "Segoe UI", "Microsoft YaHei", sans-serif';ctx.fillStyle='#53645a';ctx.fillText(subtitle,1240,140,2240);
    if(instrumentation){ctx.font='22px "Segoe UI", "Microsoft YaHei", sans-serif';ctx.fillText(`I · ${instrumentation[0]}`,1240,177,2240);ctx.fillText(`II · ${instrumentation[1]}`,1240,210,2240);}
    const top=instrumentation?240:185,scale=Math.min(2320/width,(3375-top)/height),w=width*scale,h=height*scale;ctx.drawImage(image,(2480-w)/2,top,w,h);
    ctx.fillStyle='#53645a';ctx.font='26px "Segoe UI", "Microsoft YaHei", sans-serif';ctx.fillText(`Page ${page} / ${total}`,1240,3450);
    const blob=await new Promise<Blob>((resolve,reject)=>canvas.toBlob(b=>b?resolve(b):reject(Error('PNG export failed')),'image/png'));
    return pngResolution(new Uint8Array(await blob.arrayBuffer()));
  }finally{URL.revokeObjectURL(url);}
}
export function pngResolution(bytes:Uint8Array<ArrayBuffer>){
  const chunk=new Uint8Array(21),view=new DataView(chunk.buffer);view.setUint32(0,9);chunk.set(new TextEncoder().encode('pHYs'),4);view.setUint32(8,11811);view.setUint32(12,11811);chunk[16]=1;
  let crc=0xffffffff;for(const value of chunk.slice(4,17)){crc^=value;for(let bit=0;bit<8;bit++)crc=(crc>>>1)^((crc&1)?0xedb88320:0);}view.setUint32(17,(crc^0xffffffff)>>>0);
  const parts=[bytes.slice(0,33),chunk];let at=33;const source=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);
  while(at<bytes.length){const length=source.getUint32(at)+12;if(at+length>bytes.length)throw Error('Invalid PNG');if(new TextDecoder().decode(bytes.slice(at+4,at+8))!=='pHYs')parts.push(bytes.slice(at,at+length));at+=length;}
  const result=new Uint8Array(parts.reduce((n,p)=>n+p.length,0));at=0;for(const part of parts){result.set(part,at);at+=part.length;}return result;
}
