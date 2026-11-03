import fs from 'node:fs/promises';
import {Workbook, SpreadsheetFile} from '@oai/artifact-tool';

const dir = new URL('.', import.meta.url).pathname;
const wb=Workbook.create();
const g=wb.worksheets.add('Matchup Graphic');
const inp=wb.worksheets.add('Inputs');
const c={navy:'#0C2C50',gold:'#E4BD72',paper:'#EDF1F5',white:'#FFFFFF',muted:'#52677E',light:'#DCE5EF',blue:'#315B83',amber:'#FFF2CC'};
for(const s of [g,inp]) {s.showGridLines=false;}
g.tabColor=c.navy; inp.tabColor=c.gold;
g.getRange('A1:Z47').format={fill:c.paper,font:{name:'Arial',size:13,color:c.navy},verticalAlignment:'center',rowHeightPx:28,columnWidthPx:40};
const heights={1:20,2:32,3:38,4:38,5:32,6:5,7:18,8:34,9:34,10:26,11:26,12:18,13:28,14:28,15:36,16:36,17:36,18:26,19:26,20:18,21:38,22:34,23:30,24:40,25:40,26:40,27:40,28:40,29:40,30:40,31:40,32:18,33:34,34:27,35:27,36:27,37:27,38:18,39:34,40:26,41:26,42:26,43:26,44:18,45:30,46:28,47:18};
for (const [r,h] of Object.entries(heights)) g.getRange(`A${r}:Z${r}`).format.rowHeightPx=h;
function block(s,range,value,{fill=c.white,size=13,color=c.navy,bold=false,align='center',formula=false,wrap=false,fmt}={}){
  const r=s.getRange(range);r.merge();
  r.format={fill,font:{name:'Arial',size,color,bold},horizontalAlignment:align,verticalAlignment:'center',wrapText:wrap};
  const first=range.split(':')[0];
  s.getRange(first)[formula?'formulas':'values']=[[value]];
  if(fmt)r.setNumberFormat(fmt);
}
const link=(cell)=>`=IF(ISBLANK('Inputs'!${cell}),"—",'Inputs'!${cell})`;
function linked(range,cell,opts={}){block(g,range,link(cell),{formula:true,...opts});}
g.getRange('A1:Z6').format.fill=c.navy;
block(g,'B2:R2','@BG.ANALYTICS   /   COLLEGE FOOTBALL',{fill:c.navy,color:c.gold,bold:true,align:'left',size:13});
block(g,'S2:Y2','PREGAME',{fill:c.navy,color:c.gold,bold:true,size:12});
block(g,'B3:Y4','MATCHUP BREAKDOWN',{fill:c.navy,color:c.white,bold:true,align:'left',size:34});
linked('B5:Y5','B6',{fill:c.navy,color:c.white,align:'left',size:12});
g.getRange('A6:Z6').format.fill=c.gold;
linked('B8:L9','B9',{fill:c.navy,color:c.white,bold:true,size:27,wrap:true});
linked('O8:Y9','C9',{fill:c.blue,color:c.white,bold:true,size:27,wrap:true});
block(g,'M8:N11','VS',{fill:c.paper,bold:true,size:18});
block(g,'B10:L11',`='Inputs'!B10&"  /  "&'Inputs'!B11`,{formula:true,fill:c.light,bold:true,size:13});
block(g,'O10:Y11',`='Inputs'!C10&"  /  "&'Inputs'!C11`,{formula:true,fill:c.light,bold:true,size:13});
block(g,'B13:L14','MODEL PROJECTED POINTS',{fill:c.navy,color:c.gold,bold:true,size:13});
block(g,'O13:Y14','MODEL PROJECTED POINTS',{fill:c.blue,color:c.white,bold:true,size:13});
linked('B15:L17','B12',{size:54,bold:true,fmt:'0.0'});
linked('O15:Y17','C12',{size:54,bold:true,fmt:'0.0'});
block(g,'B18:G19','WIN PROBABILITY',{fill:c.light,bold:true,size:12});
linked('H18:L19','B13',{fill:c.light,bold:true,size:23,fmt:'0%'});
block(g,'O18:T19','WIN PROBABILITY',{fill:c.light,bold:true,size:12});
linked('U18:Y19','C13',{fill:c.light,bold:true,size:23,fmt:'0%'});
block(g,'B21:Y21','THE MATCHUP   /   OFFENSE vs. OPPOSING DEFENSE',{fill:c.navy,color:c.white,bold:true,size:16});
block(g,'B22:L22',`='Inputs'!B9&" HAS THE BALL"`,{formula:true,fill:c.gold,bold:true,size:13});
block(g,'O22:Y22',`='Inputs'!C9&" HAS THE BALL"`,{formula:true,fill:c.gold,bold:true,size:13});
for (const [metric,off,def] of [['B23:F23','G23:I23','J23:L23'],['O23:S23','T23:V23','W23:Y23']]) {
 block(g,metric,'METRIC',{fill:c.light,bold:true,size:11});
 block(g,off,'OFFENSE',{fill:c.light,bold:true,size:11});
 block(g,def,'DEFENSE',{fill:c.light,bold:true,size:11});
}
const metrics=[
 ['PPA / play','ppa','0.000',.245,.11,.201,.135,'Higher on offense; lower allowed on defense.'],
 ['Success rate','successrate','0.0%',.468,.392,.443,.405,'Higher on offense; lower allowed on defense.'],
 ['Explosiveness','explosiveness','0.00',1.34,1.18,1.29,1.22,'PPA on successful plays, not explosive-play percentage.'],
 ['Pass PPA','passingplays_ppa','0.000',.32,.16,.28,.19,'Passing-play PPA. Higher on offense; lower allowed on defense.'],
 ['Rush PPA','rushingplays_ppa','0.000',.18,.07,.14,.09,'Rushing-play PPA. Higher on offense; lower allowed on defense.'],
 ['Line yards','lineyards','0.00',2.91,2.45,2.78,2.61,'Higher on offense; lower allowed on defense.'],
 ['Stuff rate','stuffrate','0.0%',.151,.224,.173,.207,'Lower on offense; higher on defense.'],
 ['Points / opp.','pointsperopportunity','0.00',4.61,3.72,4.28,3.94,'Points per scoring opportunity. Higher on offense; lower allowed on defense.']
];
for(let i=0;i<8;i++){
 const r=24+i, ir=19+i, bg=i%2? '#F5F7FA':c.white;
 block(g,`B${r}:F${r}`,metrics[i][0],{fill:bg,align:'left',size:13});
 block(g,`O${r}:S${r}`,metrics[i][0],{fill:bg,align:'left',size:13});
 for (const [range,source] of [[`G${r}:I${r}`,`B${ir}`],[`J${r}:L${r}`,`E${ir}`],[`T${r}:V${r}`,`D${ir}`],[`W${r}:Y${r}`,`C${ir}`]]) linked(range,source,{fill:bg,bold:true,size:17,fmt:metrics[i][2]});
}
block(g,'B33:L33','KEY MATCHUP',{fill:c.navy,color:c.gold,bold:true,size:14});
block(g,'O33:Y33','WHAT COULD SWING IT',{fill:c.navy,color:c.gold,bold:true,size:14});
linked('B34:L37','B29',{wrap:true,align:'left',size:15});
linked('O34:Y37','B30',{wrap:true,align:'left',size:15});
block(g,'B39:Y39','MY READ',{fill:c.gold,bold:true,align:'left',size:14});
linked('B40:Y43','B31',{wrap:true,align:'left',size:17,bold:true});
g.getRange('A45:Z47').format.fill=c.navy;
linked('B45:Y45','B7',{fill:c.navy,color:c.white,align:'left',size:11});
linked('B46:Y46','B5',{fill:c.navy,color:c.gold,align:'left',size:11,bold:true});

inp.getRange('A1:I43').format={font:{name:'Arial',size:11,color:c.navy},verticalAlignment:'center',rowHeight:25,columnWidth:18};
inp.getRange('A1:A43').format.columnWidth=29;
inp.getRange('F1:F43').format.columnWidth=3;
inp.getRange('G1:H43').format.columnWidth=43;
inp.getRange('I1:I43').format.columnWidth=85;
inp.getRange('A1').values=[['MATCHUP INPUTS']];inp.getRange('A1').format.font={bold:true,size:18,color:c.navy};
inp.getRange('A2').values=[['Edit amber cells. The graphic updates from these inputs. Sample numbers are illustrative.']];
inp.getRange('A3').values=[['To share: select Matchup Graphic!A1:Z47, then Excel Copy as Picture. Replace the demo label after entering verified data.']];
inp.getRange('A5:A7').values=[['Graphic status'],['Game details'],['Stats coverage']];
inp.getRange('B5').values=[['DESIGN DEMO — ILLUSTRATIVE VALUES']];
inp.getRange('B6').values=[['WEEK XX   /   SAT, MONTH DD   /   KICKOFF ET   /   VENUE']];
inp.getRange('B7').values=[['Season-to-date stats through Week XX. PPA = predicted points added.']];
inp.getRange('A8:C8').values=[['TEAM DETAILS','TEAM A','TEAM B']];
inp.getRange('A9:C13').values=[['Team name','TEAM A','TEAM B'],['Record / conference','6–1   /   CONFERENCE','5–2   /   CONFERENCE'],['Site','AWAY','HOME'],['Projected points',31,27],['Win probability',.62,.38]];
inp.getRange('A15').values=[['Projection sources: game_predictions_full. Map home/away columns to the correct team.']];
inp.getRange('A16').values=[['Projected points: homepoints / awaypoints. Win probability: homewinprob / awaywinprob.']];
inp.getRange('A18:I18').values=[['METRIC','A OFFENSE','A DEFENSE','B OFFENSE','B DEFENSE',null,'OFFENSE SOURCE COLUMN','DEFENSE SOURCE COLUMN','INTERPRETATION']];
inp.getRange('A19:I26').values=metrics.map(m=>[m[0],m[3],m[4],m[5],m[6],null,'offense_'+m[1],'defense_'+m[1],m[7]]);
inp.getRange('A28:B28').values=[['EDITORIAL','EDITABLE COPY']];
inp.getRange('A29:B31').values=[['Key matchup','Can Team A’s passing attack sustain drives against Team B’s coverage?'],['Swing factor','Watch early-down rushing efficiency and which front creates more stuffed runs.'],['My read','Add your matchup takeaway here. Explain the advantage, the likely game script, and the path to an upset.']];
inp.getRange('A33').values=[['SOURCE MAP & USE']];
inp.getRange('A34').values=[['Metric availability: BG.Analytics.CFB/Model Testing/team_advanced_season_stats.csv (local schema).']];
inp.getRange('A35').values=[['Projection availability: BG.Analytics.CFB/Model Testing/game_predictions_full.csv (local schema).']];
inp.getRange('A36').values=[['All numbers here are invented demo values, not observed team statistics or current predictions.']];
inp.getRange('A37').values=[['Use one season and one verified pregame cutoff. Season aggregates are not automatically rewound to an earlier week.']];
inp.getRange('A38').values=[['Enter rates as percentages (46.8%) or decimals (0.468). Leave missing inputs empty; the graphic displays a dash.']];
inp.getRange('A39').values=[['Offense is paired with the opposing defense. These are descriptive season rates, not an opponent-adjusted edge score.']];
inp.getRange('A40').values=[['Style: navy #0C2C50, gold #E4BD72, blue #315B83. Change the team-header fills to use school colors.']];
inp.getRange('A41').values=[['Optional: insert team logos over each team-name panel and keep the center VS gutter clear.']];
inp.getRange('A42').values=[['Presentation formulas are editable. The workbook does not connect to a database or refresh stats automatically.']];
for(const range of ['A8:C8','A18:E18','G18:I18','A28:B28'])inp.getRange(range).format={fill:c.navy,font:{bold:true,color:c.white},horizontalAlignment:'center'};
for(const range of ['B5:B7','B9:C13','B19:E26','B29:B31'])inp.getRange(range).format.fill=c.amber;
inp.getRange('B13:C13').setNumberFormat('0.0%');
inp.getRange('B12:C12').setNumberFormat('0.0');
for(let i=0;i<8;i++)inp.getRange(`B${19+i}:E${19+i}`).setNumberFormat(metrics[i][2]);
inp.getRange('B13:C13').dataValidation={rule:{type:'decimal',operator:'between',formula1:0,formula2:1}};
inp.getRange('B11:C11').dataValidation={rule:{type:'list',values:['HOME','AWAY','NEUTRAL']}};
inp.freezePanes.freezeRows(3);
inp.getRange('B9:C11').format.wrapText=true;
inp.getRange('A9:E11').format.rowHeight=38;
inp.getRange('B28:E28').merge();
for(const r of [2,3,15,16,34,35,36,37,38,39,40,41,42]){
 inp.getRange(`A${r}:E${r}`).merge();
 inp.getRange(`A${r}:E${r}`).format.wrapText=true;
 inp.getRange(`A${r}:E${r}`).format.rowHeight=r===2?30:40;
}
for(const r of [5,6,7,29,30,31]){
 inp.getRange(`B${r}:E${r}`).merge();
 inp.getRange(`B${r}:E${r}`).format.fill=c.amber;
 inp.getRange(`B${r}:E${r}`).format.wrapText=true;
 inp.getRange(`A${r}:E${r}`).format.rowHeight=r>=29?48:35;
}

// Exercise the links, including a true zero and missing input, then restore the demo.
inp.getRange('B19').values=[[0]];
wb.recalculate();
console.log('ZERO',JSON.stringify(g.getRange('G24').values));
if(g.getRange('G24').values[0][0]!==0)throw new Error('Zero failed');
inp.getRange('B19').values=[[null]];
wb.recalculate();
if(g.getRange('G24').values[0][0]!=='—')throw new Error('Blank failed');
inp.getRange('B19').values=[[metrics[0][3]]];
inp.getRange('E26').values=[[9.99]];
wb.recalculate();
if(g.getRange('J31').values[0][0]!==9.99)throw new Error('Opposing defense link failed');
inp.getRange('E26').values=[[metrics[7][6]]];
wb.recalculate();
console.log((await wb.inspect({kind:'region',sheetId:'Matchup Graphic',range:'B23:L31',maxChars:1800,tableMaxRows:9,tableMaxCols:11})).ndjson);
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:30},summary:'Formula error scan'})).ndjson);
for (const [name,range,file] of [['Matchup Graphic','A1:Z47','preview.png'],['Inputs','A1:E42','inputs-preview.png'],['Inputs','G18:I26','source-map-preview.png']]){
 const image=await wb.render({sheetName:name,range,scale:1,format:'png'});
 await fs.writeFile(dir+file,new Uint8Array(await image.arrayBuffer()));
}
const output=await SpreadsheetFile.exportXlsx(wb);await output.save(dir+'BG_Analytics_Matchup_Template.xlsx');
console.log('Saved workbook and previews.');
