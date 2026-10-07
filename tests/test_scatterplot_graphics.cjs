const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const template=fs.readFileSync(path.join(__dirname,'../app/utils/scatterplot.html'),'utf8');
const point=(name,x,y)=>({name,x,y,conference:'SEC',detail:'Season statistics',logo:''});
const config=(points)=>({title:'Advanced Stats',subtitle:'2026 · Season statistics',scope:'SEC',points,logoSize:56,x:{label:'Offense',rate:false,reverse:false},y:{label:'Defense',rate:false,reverse:false}});
async function render(config,deny=false){
 const drawn=[],elements={},canvases=[],copied=[];
 function element(){return {style:{},handlers:{},textContent:'',addEventListener(event,fn){this.handlers[event]=fn},getBoundingClientRect(){return {left:0,top:0,width:2160,height:2160}}};}
 const ctx=new Proxy({},{get(target,key){if(key==='measureText')return t=>({width:String(t).length*18});if(key==='fillText')return (...args)=>drawn.push(args);if(key in target)return target[key];return (...args)=>args.forEach(a=>{if(typeof a==='number')assert.ok(Number.isFinite(a));});},set(t,k,v){t[k]=v;return true}});
 const sandbox={document:{getElementById(id){return elements[id] ||= element()},createElement(){const c={getContext:()=>ctx,toBlob:cb=>cb(new Blob(['image'],{type:'image/png'}))};canvases.push(c);return c;}},
 Blob,URL:{createObjectURL:()=> 'blob:preview',revokeObjectURL(){}},window:{addEventListener(){}},
 navigator:{clipboard:{write:async items=>{if(deny)throw Error('denied');copied.push(items)}}},ClipboardItem:class{constructor(items){this.items=items}},
 Image:class{set src(_){queueMicrotask(()=>this.onerror())}},setTimeout,clearTimeout};
 vm.createContext(sandbox);
 await vm.runInContext(template.match(/<script>([\s\S]*)<\/script>/)[1].replace('__SCATTER_CONFIG__',JSON.stringify(config)),sandbox);
 return {drawn,elements,canvases,copied,sandbox};
}
for(const reverseX of [false,true])for(const reverseY of [false,true])test(`axes ${reverseX}/${reverseY}`,async()=>{
 const input=config([point('A',-2,-1),point('B',4,3)]);input.x.reverse=reverseX;input.y.reverse=reverseY;
 const r=await render(input);
 assert.equal(r.canvases[0].width,2160);assert.equal(r.canvases[0].height,2160);
 const a=r.drawn.find(d=>d[0]==='A'),b=r.drawn.find(d=>d[0]==='B');
 assert.equal(a[1]>b[1],reverseX);assert.equal(a[2]<b[2],reverseY);
 assert.equal(r.elements.copy.disabled,false);
 await r.elements.copy.handlers.click();assert.equal(r.copied.length,1);
});
test('constant values, overlaps, fallback and exact hover details',async()=>{
 const r=await render(config([point('A',0,0),point('B',0,0)]),true);
 const a=r.drawn.find(d=>d[0]==='A');const b=r.drawn.find(d=>d[0]==='B');
 assert.deepEqual(a.slice(1),b.slice(1));
 r.elements.preview.handlers.mousemove({clientX:a[1],clientY:a[2]+10});
 assert.match(r.elements.tooltip.textContent,/A · SEC/);assert.match(r.elements.tooltip.textContent,/B · SEC/);
 assert.match(r.elements.status.textContent,/2 team\(s\) use initials/);
 await r.elements.copy.handlers.click();assert.match(r.elements.status.textContent,/Right-click/);
});
test('missing image, long labels and rate formatting',async()=>{
 const input=config([point('A',.25,.5)]);input.points[0].logo='data:image/png;base64,broken';
 input.title='Long title '.repeat(11);input.x.label='Long axis '.repeat(12);input.x.rate=true;
 const r=await render(input);
 assert.match(r.elements.status.textContent,/Graphic ready/);
 assert.ok(r.drawn.some(d=>String(d[0]).includes('%')));
 assert.equal(vm.runInContext('formatted(.253, {rate:true})',r.sandbox),'25.3%');
});
