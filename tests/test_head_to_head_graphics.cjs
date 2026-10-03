// Runtime checks for the browser canvas/clipboard code without network or a browser.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const template = fs.readFileSync(path.join(__dirname, '../app/utils/head_to_head_graphics.html'), 'utf8');
const team = name => ({name, logo: ''});

async function render(config) {
  const drawn=[], canvases=[], elements={};
  function element(tag) {
    return {tag, children: [], handlers: {}, textContent: '', append(...children){this.children.push(...children)},
      setAttribute(){}, addEventListener(type,fn){this.handlers[type]=fn}};
  }
  const context = new Proxy({}, {get(target,key){
    if(key==='measureText') return text=>({width:String(text).length*24});
    if(key==='fillText') return (...args)=>drawn.push(args);
    if(key in target)return target[key];
    return (...args)=>args.forEach(arg=>{if(typeof arg==='number')assert.ok(Number.isFinite(arg));});
  },set(target,key,value){target[key]=value;return true}});
  const document={getElementById(id){return elements[id] ||= element(id)},createElement(tag){
    const result=element(tag);
    if(tag==='canvas'){
      result.getContext=()=>context;result.toBlob=cb=>cb(new Blob(['png'],{type:'image/png'}));canvases.push(result);
    }
    return result;
  }};
  const code=template.match(/<script>([\s\S]*)<\/script>/)[1].replace('__H2H_CONFIG__',JSON.stringify(config));
  await vm.runInNewContext(code,{document,Blob,URL:{createObjectURL:()=> 'blob:preview'},
    navigator:{clipboard:{write:async()=>{throw new Error('permission denied')}}},ClipboardItem:class {},
    Image: class {set src(value){queueMicrotask(()=>this.onerror())}}, setTimeout,clearTimeout});
  return {drawn,canvases,elements};
}

test('top 25 renders every row, provisional status, and copy fallback', async()=>{
  const rows=Array.from({length:25},(_,i)=>({...team(`School ${i+1}`),position:i+1,record:'4–1',exceptions:1}));
  const {drawn,canvases,elements}=await render({kind:'rankings',season:2026,cutoff:'Regular season · Week 5',status:'Provisional · best found',
    slides:[{title:'HEAD TO HEAD TOP 25',subtitle:'One representative order',rows}]});
  assert.equal(canvases.length,1);assert.equal(canvases[0].width,2160);assert.equal(canvases[0].height,2700);
  for(const row of rows)assert.ok(drawn.some(args=>args[0]===row.name));
  assert.ok(drawn.some(args=>args[0].includes('PROVISIONAL')));
  assert.match(elements.status.textContent,/ready.*Missing logos/);
  const [button,feedback]=elements.slides.children[0].children[0].children;
  await button.handlers.click();assert.match(feedback.textContent,/Right-click/);
});

test('chain pages render all games and explicit no-path panel',async()=>{
  const slides=[0,1,2].map(index=>({title:'THE WIN CHAIN',subtitle:'A → Z',detail:`Part ${index+1}/3`,
    games:Array.from({length:5},(_,i)=>({winner:team(`Winner ${index*5+i}`),loser:team(`Loser ${index*5+i}`),score:'31–24',date:'2026-09-05'}))}));
  slides.push({title:'THE WIN CHAIN',subtitle:'Z → A',detail:'No win path in this direction',games:[]});
  const {drawn,canvases}=await render({kind:'chains',season:2026,cutoff:'Week 5',status:'Completed results',slides});
  assert.equal(canvases.length,4);
  for(let i=0;i<15;i++)assert.ok(drawn.some(args=>args[0]===`Winner ${i}`));
  assert.ok(drawn.some(args=>args[0]==='NO WIN PATH'));
});

for(const count of [2,3,6,16])test(`${count}-team circle renders names and appropriate evidence`,async()=>{
  const teams=Array.from({length:count},(_,i)=>team(`A School With A Very Long Name ${i}`));
  teams[0].logo='https://unavailable.example/logo.png';
  const games=teams.map((winner,i)=>({winner,loser:teams[(i+1)%count],score:`${30+i}–17`,date:'2026-09-05'}));
  const {drawn,elements}=await render({kind:'circle',season:2026,cutoff:'Week 5',status:'Completed results',
    slides:[{title:'CIRCLE OF CHAOS',subtitle:`${count} teams`,teams,games}]});
  for(const t of teams)assert.ok(drawn.some(args=>args[0].includes(t.name)));
  if(count<=6)for(const game of games)assert.ok(drawn.some(args=>args[0]===game.score));
  assert.match(elements.status.textContent,/ready/);
});
