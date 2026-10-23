/** Store PNGs without recompressing; UTF-8 filenames, one browser download. */
export function zipFiles(files:{name:string;data:Uint8Array<ArrayBuffer>}[]):Blob{
  const encoder=new TextEncoder(),parts:BlobPart[]=[],central:BlobPart[]=[];let offset=0,centralSize=0;
  const table=Uint32Array.from({length:256},(_,i)=>{let c=i;for(let k=0;k<8;k++)c=(c>>>1)^((c&1)?0xedb88320:0);return c>>>0;});
  for(const file of files){
    const name=encoder.encode(file.name);let crc=0xffffffff;for(const value of file.data)crc=table[(crc^value)&255]^(crc>>>8);crc=(crc^0xffffffff)>>>0;
    const header=new Uint8Array(30+name.length),view=new DataView(header.buffer);
    view.setUint32(0,0x04034b50,true);view.setUint16(4,20,true);view.setUint16(6,0x800,true);view.setUint16(12,33,true);view.setUint32(14,crc,true);view.setUint32(18,file.data.length,true);view.setUint32(22,file.data.length,true);view.setUint16(26,name.length,true);header.set(name,30);
    const entry=new Uint8Array(46+name.length),cv=new DataView(entry.buffer);
    cv.setUint32(0,0x02014b50,true);cv.setUint16(4,20,true);cv.setUint16(6,20,true);cv.setUint16(8,0x800,true);cv.setUint16(14,33,true);cv.setUint32(16,crc,true);cv.setUint32(20,file.data.length,true);cv.setUint32(24,file.data.length,true);cv.setUint16(28,name.length,true);cv.setUint32(42,offset,true);entry.set(name,46);
    parts.push(header,file.data);central.push(entry);offset+=header.length+file.data.length;centralSize+=entry.length;
  }
  const end=new Uint8Array(22),v=new DataView(end.buffer);v.setUint32(0,0x06054b50,true);v.setUint16(8,files.length,true);v.setUint16(10,files.length,true);v.setUint32(12,centralSize,true);v.setUint32(16,offset,true);
  return new Blob([...parts,...central,end],{type:'application/zip'});
}
