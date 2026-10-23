export const PAGE_WIDTH=840;
export function songTitle(name?:string){return (name||'Score').replace(/\.(mp3|flac)$/i,'').replace(/^.*?\s+-\s+/,'').replace(/^[《]|[》]$/g,'').trim()||'Score';}
export function pageFileName(title:string,page:number){return `《${title.replace(/[<>:"/\\|?*\x00-\x1f]/g,'_')}》Page_${page}.png`;}
export function saveBlob(blob:Blob,name:string){const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),2000);}
/** Export clean engraving only; interactive hitboxes/highlighting never enter PNGs. */
export async function pagePng(source:SVGSVGElement,title:string,subtitle:string,page:number,total:number):Promise<Uint8Array<ArrayBuffer>>{
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
    const scale=Math.min(2320/width,3190/height),w=width*scale,h=height*scale;ctx.drawImage(image,(2480-w)/2,185,w,h);
    ctx.fillStyle='#53645a';ctx.font='26px "Segoe UI", "Microsoft YaHei", sans-serif';ctx.fillText(`Page ${page} / ${total}`,1240,3450);
    const blob=await new Promise<Blob>((resolve,reject)=>canvas.toBlob(b=>b?resolve(b):reject(Error('PNG export failed')),'image/png'));
    return new Uint8Array(await blob.arrayBuffer());
  }finally{URL.revokeObjectURL(url);}
}
