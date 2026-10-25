import test from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
const built=await build({entryPoints:['workers/checker/upstream.js'],bundle:true,write:false,format:'esm',platform:'node',plugins:[{name:'no-network',setup(b){b.onResolve({filter:/^cloudflare:sockets$/},()=>({path:'socket',namespace:'mock'}));b.onLoad({filter:/.*/,namespace:'mock'},()=>({contents:'export function connect(){throw Error("Network forbidden in protocol tests")}' }));}}]});
const { createSstpReceiveQueue: queue, createTcpOverPppSession: tcp }=await import('data:text/javascript;base64,'+Buffer.from(built.outputFiles[0].text).toString('base64'));
const bytes=(...values)=>new Uint8Array(values);
const flatten=r=>Array.from(Buffer.concat(r.chunks.map(c=>Buffer.from(c))));
test('retransmitted bytes are never delivered twice; overlap delivers only new tail',()=>{
  const q=queue(100);
  assert.deepEqual(flatten(q.accept(100,bytes(1,2,3))),[1,2,3]);
  assert.deepEqual(flatten(q.accept(100,bytes(1,2,3))),[]);
  assert.deepEqual(flatten(q.accept(101,bytes(2,3,4,5))),[4,5]);
  assert.equal(q.stats.duplicate_segments,1);assert.equal(q.stats.overlap_segments,1);
});
test('out of order and overlapping queued segments form one contiguous stream',()=>{
  const q=queue(100);
  assert.deepEqual(flatten(q.accept(103,bytes(4,5))),[]);
  const r=q.accept(100,bytes(1,2,3));assert.deepEqual(flatten(r),[1,2,3,4,5]);assert.equal(r.next,105);
  const p=queue(100);p.accept(102,bytes(3,4,5));assert.deepEqual(flatten(p.accept(100,bytes(1,2,3,4))),[1,2,3,4,5]);
});
test('sequence wraparound and FIN cannot close a stream before missing bytes',()=>{
  const q=queue(0xfffffffe);assert.equal(q.accept(0xfffffffe,bytes(1,2,3)).next,1);
  assert.deepEqual(flatten(q.accept(0,bytes(3,4))),[4]);
  const p=queue(100);assert.equal(p.accept(103,bytes(),true).finished,false);
  assert.equal(p.accept(100,bytes(1,2,3)).finished,true);
  assert.equal(queue(105).accept(100,bytes(1,2,3,4),true).finished,false);
});
test('out-of-order buffering is bounded and cannot move acknowledgement across a gap',()=>{
  const q=queue(100,4);const r=q.accept(110,bytes(1,2,3,4,5));
  assert.equal(r.next,100);assert.equal(r.chunks.length,0);assert.equal(q.stats.buffer_limit_drops,1);
});
test('window scaling is opt-in, and SYN header lengths and checksum cover its options',()=>{
  const old=tcp({},'10.0.0.1','1.1.1.1',443).buildTcpFrame(2);assert.equal(old.length,48);assert.equal(old[40],0x50);
  const frame=tcp({},'10.0.0.1','1.1.1.1',443,2).buildTcpFrame(2);
  assert.equal(frame.length,56);assert.equal(frame[40],0x70);assert.equal(new DataView(frame.buffer).getUint16(10),48);
  assert.deepEqual(Array.from(frame.subarray(48)),[2,4,5,120,1,3,3,2]);
  const pseudo=new Uint8Array(12+28);pseudo.set([10,0,0,1,1,1,1,1,0,6,0,28]);pseudo.set(frame.subarray(28),12);
  let sum=0;for(let i=0;i<pseudo.length;i+=2)sum+=(pseudo[i]<<8)|pseudo[i+1];while(sum>>16)sum=(sum&0xffff)+(sum>>16);
  assert.equal(sum,0xffff);assert.throws(()=>tcp({},'10.0.0.1','1.1.1.1',443,3));
});
test('IP padding and malformed/fragmented TCP packets do not enter the TLS payload',()=>{
  const session=tcp({},'10.0.0.1','1.1.1.1',443);const syn=session.buildTcpFrame(2);
  const packet=new Uint8Array(51), view=new DataView(packet.buffer);
  packet[0]=0x45;packet[9]=6;view.setUint16(2,43);view.setUint16(20,443);view.setUint16(22,new DataView(syn.buffer).getUint16(28));packet[32]=0x50;
  assert.equal(session.matchIncomingIpPacket(packet).payloadEnd,43);
  packet[32]=0x40;assert.equal(session.matchIncomingIpPacket(packet),null);
  packet[32]=0x50;view.setUint16(6,1);assert.equal(session.matchIncomingIpPacket(packet),null);
});
