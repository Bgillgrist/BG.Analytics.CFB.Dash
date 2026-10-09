const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const template=fs.readFileSync(path.join(__dirname,'../app/utils/scatterplot.html'),'utf8');
const point=(name,x,y)=>({name,x,y,conference:'SEC',detail:'Season statistics',logo:''});
const config=(points)=>({title:'Advanced Stats',subtitle:'2026 · Season statistics',scope:'SEC',points,logoSize:56,x:{label:'Offense',rate:false,reverse:false},y:{label:'Defense',rate:false,reverse:false}});
async function render(config,deny=false,storage=new Map()){
 const drawn=[],elements={},canvases=[],copied=[],calls=[];
 function element(){return {style:{},setPointerCapture(){},handlers:{},textContent:'',addEventListener(event,fn){this.handlers[event]=fn},getBoundingClientRect(){return {left:0,top:0,width:2160,height:2160}}};}
 const ctx=new Proxy({},{get(target,key){if(key==='measureText')return t=>({width:String(t).length*18});if(key==='fillText')return (...args)=>drawn.push(args);if(key in target)return target[key];return (...args)=>{calls.push([key,...args]);args.forEach(a=>{if(typeof a==='number')assert.ok(Number.isFinite(a));});};},set(t,k,v){t[k]=v;return true}});
 const sandbox={document:{getElementById(id){return elements[id] ||= element()},createElement(){const c={getContext:()=>ctx,toBlob:cb=>cb(new Blob(['image'],{type:'image/png'}))};canvases.push(c);return c;}},
 sessionStorage:{getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value)},Blob,URL:{createObjectURL:()=> 'blob:preview',revokeObjectURL(){}},window:{addEventListener(){}},
 navigator:{clipboard:{write:async items=>{if(deny)throw Error('denied');copied.push(items)}}},ClipboardItem:class{constructor(items){this.items=items}},
 Image:class{set src(value){queueMicrotask(()=>value==='brand-image'?this.onload():this.onerror())}},setTimeout,clearTimeout};
 vm.createContext(sandbox);
 await vm.runInContext(template.match(/<script>([\s\S]*)<\/script>/)[1].replace('__SCATTER_CONFIG__',JSON.stringify(config)),sandbox);
 return {drawn,elements,canvases,copied,sandbox,calls};
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

test('median dividers use plotted medians and respect reversals',async()=>{
 for(const reverse of [false,true]){
  const input=config([point('A',0,-10),point('B',2,5),point('C',100,6)]);input.x.reverse=reverse;input.y.reverse=reverse;
  const r=await render(input);
  assert.equal(vm.runInContext('median([100,0,2])',r.sandbox),2);
  assert.equal(vm.runInContext('median([10,2,0,4])',r.sandbox),3);
  const expectedX=vm.runInContext(`position(2,domain([0,2,100]),280,2010,${reverse})`,r.sandbox);
  assert.ok(r.calls.some(c=>c[0]==='moveTo'&&c[1]===expectedX));
  assert.ok(r.calls.some(c=>c[0]==='setLineDash'&&c[1][0]===14));
 }
});
test('labels can be edited, dragged, copied and restored across rerenders',async()=>{
 const storage=new Map(),input=config([point('A',0,0),point('B',10,10)]);input.layoutKey='test';
 const r=await render(input,false,storage),e=r.elements;
 await e.copy.handlers.click();const first=r.copied[0][0].items['image/png'];
 await e.q0.handlers.input({target:{value:'Great Offense, Bad Defense'}});
 let label=r.drawn.filter(d=>d[0]==='Great Offense, Bad Defense').at(-1);assert.ok(label);
 const oldX=label[1];
 e.preview.handlers.pointerdown({button:0,clientX:label[1],clientY:label[2]+20,pointerId:1,preventDefault(){}});
 await e.preview.handlers.pointermove({clientX:label[1]+150,clientY:label[2]+80});
 e.preview.handlers.pointerup();
 label=r.drawn.filter(d=>d[0]==='Great Offense, Bad Defense').at(-1);assert.ok(label[1]>oldX);
 await e.copy.handlers.click();assert.notEqual(r.copied.at(-1)[0].items['image/png'],first);
 const restored=await render(input,false,storage);
 assert.equal(restored.elements.q0.value,'Great Offense, Bad Defense');
 assert.equal(restored.elements.qx0.value,e.qx0.value);
 await e.q0.handlers.input({target:{value:''}});
 assert.equal(JSON.parse(storage.get('scatter-labels-v1-test'))[0].text,'');
});
test('footer uses cropped PNG logo and larger centered branding',async()=>{
 const input=config([point('A',0,0)]);input.brandLogo='brand-image';input.brandBounds=[389,963,3033,2426];
 const r=await render(input);
 const image=r.calls.find(c=>c[0]==='drawImage'&&c.length===10);
 assert.ok(image);assert.equal(image[3],963);
 assert.equal(image[7]+image[9]/2,2090);
 assert.ok(!r.drawn.some(d=>String(d[0]).includes('TEAM LOGO SCATTERPLOT')));
});
