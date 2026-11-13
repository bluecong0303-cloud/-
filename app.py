"""플레이 건 플 — Python 3.10+, streamlit run app.py.
GitHub에 app.py 및 requirements.txt를 업로드한 뒤 Streamlit Cloud에서 app.py 배포.
브라우저 Canvas 기반 레이캐스팅 FPS. 외부 이미지/오디오/CDN 없음.
데스크톱 Chrome/Edge 권장. 마우스 잠금은 브라우저 정책에 따라 제한될 수 있음.
"""
import streamlit as st
import streamlit.components.v1 as components

GAME = r'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
*{box-sizing:border-box}html,body{margin:0;background:#101719;color:#eef5ee;font-family:system-ui,sans-serif}#wrap{position:relative;width:100%;height:760px;overflow:hidden;background:#101719}canvas{width:100%;height:100%;display:block;cursor:crosshair}.panel{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;background:#071110eF;z-index:5}.card{max-width:760px;width:94%;padding:28px;border:1px solid #577568;border-radius:22px;background:linear-gradient(140deg,#253c32,#101b1c);text-align:center;box-shadow:0 24px 90px #0008}h1{font-size:clamp(30px,5vw,56px);margin:2px 0;letter-spacing:3px}.small{font-size:13px;color:#c1d4c8;line-height:1.8}button,select{padding:12px 20px;border-radius:9px;border:1px solid #8ba38b;background:#243c32;color:#fff;font-size:15px;margin:6px;cursor:pointer}button.primary{background:#dcf89e;color:#17231a;font-weight:800}#hud{position:absolute;top:16px;left:18px;right:18px;display:flex;justify-content:space-between;pointer-events:none;text-shadow:0 2px 4px black;font-weight:700;font-size:15px}#bottom{position:absolute;bottom:20px;left:20px;right:20px;display:flex;justify-content:space-between;pointer-events:none;text-shadow:0 2px 5px black}#notice{position:absolute;top:72px;left:10%;width:80%;text-align:center;color:#e6ffa6;pointer-events:none}#toolbar{position:absolute;top:110px;right:10px;z-index:2}#toolbar button{display:block;font-size:12px;padding:8px;background:#172b28bd}.hidden{display:none!important}#logo{width:260px;height:126px;margin:auto;display:block}
</style></head><body><div id="wrap"><canvas id="view" tabindex="0" aria-label="FPS 게임 화면"></canvas><div id="hud"><span id="team"></span><span id="timer"></span><span id="score"></span></div><div id="notice"></div><div id="bottom"><span id="health"></span><span id="ammo"></span></div><div id="toolbar"><button id="pause">⏸ 메뉴 / ESC</button><button id="sound">🔊 소리 켜짐</button></div><div class="panel" id="menu"><div class="card"><canvas id="logo" width="520" height="252"></canvas><h1>플레이 건 플</h1><p>TACTICAL ARENA · 3 VS 3</p><p class="small">콘크리트 훈련장, 세 명의 팀. 먼저 15킬을 달성하세요.<br>당신 + 아군 AI 2명 vs 적군 AI 3명 · 3분 경기 · 사망 후 3초 뒤 부활</p><select id="weapon" aria-label="시작 총기"></select><button class="primary" id="start">게임 시작</button><p class="small">WASD 이동 · 마우스 시점 · 좌클릭 발사 · 우클릭 조준 · R 재장전<br>1~6 총기 선택 · Shift 달리기 · ESC 일시정지<br>마우스 잠금 불가 시 드래그로 시점 / ← → 회전 · 소리는 시작 후 활성화됩니다.<br>PC 키보드·마우스 전용 / 레트로 레이캐스팅 3D</p><p class="small" id="result"></p></div></div></div><script>
'use strict';
const canvas=document.getElementById('view'),ctx=canvas.getContext('2d'),menu=document.getElementById('menu');
const $=id=>document.getElementById(id);
const TAU=Math.PI*2, FOV=Math.PI/3, limit=15, duration=180;
const weapons=[
{name:'벡터',mag:25,dmg:17,rate:.075,reload:1.7,spread:.045,range:11,color:'#626f72',auto:true},
{name:'리볼버',mag:6,dmg:62,rate:.43,reload:2.2,spread:.014,range:19,color:'#afafb0',auto:false},
{name:'일반 권총',mag:15,dmg:29,rate:.23,reload:1.4,spread:.024,range:15,color:'#48535d',auto:false},
{name:'M4',mag:30,dmg:28,rate:.105,reload:1.9,spread:.023,range:21,color:'#53615b',auto:true},
{name:'M16',mag:30,dmg:33,rate:.16,reload:2,spread:.016,range:23,color:'#50585c',auto:true},
{name:'AK 47',mag:30,dmg:38,rate:.14,reload:2.3,spread:.034,range:22,color:'#886b4d',auto:true}
];
weapons.forEach((w,i)=>{let o=document.createElement('option');o.value=i;o.textContent=`${i+1} · ${w.name}`;$('weapon').appendChild(o)});$('weapon').value='3';
const map=[
'11111111111111111111',
'10000000000000000001',
'10000000000000000001',
'10001100011000110001',
'10001100011000110001',
'10000000000000000001',
'10000011000011000001',
'10000011000011000001',
'10000000000000000001',
'10011000000000011001',
'10011000000000011001',
'10000000000000000001',
'10000001100110000001',
'10000001100110000001',
'10000000000000000001',
'10011000000000110001',
'10011000000000110001',
'10000000000000000001',
'10000000000000000001',
'11111111111111111111'];
let W=960,H=640,started=false,paused=true,ended=false,muted=false,audio=null;
let player,bots=[],scores=[0,0],remaining=duration,keys={},shooting=false,aim=false,drag=false,weaponIndex=3,ammo=[],reload=0,cooldown=0,flash=0,hit=0,damageFlash=0,step=0,bob=0,total=0,last=0,noteTime=0,death=0;
const wall=(x,y)=>!map[Math.floor(y)]||map[Math.floor(y)][Math.floor(x)]!=='0';
function clearAt(x,y){const r=.2;return !wall(x-r,y-r)&&!wall(x+r,y-r)&&!wall(x-r,y+r)&&!wall(x+r,y+r)}
function move(e,dx,dy){if(clearAt(e.x+dx,e.y))e.x+=dx;if(clearAt(e.x,e.y+dy))e.y+=dy}
function ray(x,y,a,max=30){let d=0;while(d<max){if(wall(x+Math.cos(a)*d,y+Math.sin(a)*d))break;d+=.035}return d}
function visible(a,b){let d=Math.hypot(b.x-a.x,b.y-a.y);return ray(a.x,a.y,Math.atan2(b.y-a.y,b.x-a.x),d+.1)>=d-.12}
function angle(a){return Math.atan2(Math.sin(a),Math.cos(a))}
function initAudio(){if(!audio){const A=window.AudioContext||window.webkitAudioContext;if(A)audio=new A()}if(audio&&audio.state==='suspended')audio.resume().catch(()=>{})}
function sound(kind,pitch=1,volume=1){if(!audio||muted)return;let len=kind==='step'?.08:.13,n=audio.createBuffer(1,Math.floor(audio.sampleRate*len),audio.sampleRate),d=n.getChannelData(0);for(let i=0;i<d.length;i++)d[i]=(Math.random()*2-1)*Math.pow(1-i/d.length,3);let s=audio.createBufferSource(),f=audio.createBiquadFilter(),g=audio.createGain();s.buffer=n;f.type='lowpass';f.frequency=kind==='step'?210:1800*pitch;g.gain.value=(kind==='step'?.18:.32)*volume;s.connect(f);f.connect(g);g.connect(audio.destination);s.start();s.onended=()=>{s.disconnect();f.disconnect();g.disconnect()}}
function notice(t){$('notice').textContent=t;noteTime=3}
function spawn(team){let points=team===0?[[2.5,17.5],[4.5,18.2],[1.8,15.5],[7.5,17.5]]:[[17.5,2.5],[15.5,1.8],[18.2,5.5],[12.5,2.5]];let p=points[Math.floor(Math.random()*points.length)];return {x:p[0],y:p[1]}}
function reset(){player={...spawn(0),a:-Math.PI/2,hp:100,shield:2};bots=[];for(let i=0;i<5;i++)bots.push({...spawn(i<2?0:1),team:i<2?0:1,hp:100,dead:0,cool:Math.random(),path:[],think:0,shield:1.5});scores=[0,0];remaining=duration;weaponIndex=Number($('weapon').value);ammo=weapons.map(w=>w.mag);reload=0;cooldown=0;death=0;flash=0;hit=0;damageFlash=0;total=0;ended=false;started=true;resume()}
function lock(){try{const p=canvas.requestPointerLock?.();if(p&&p.catch)p.catch(()=>notice('드래그로 시점 이동 가능 · 화살표로도 회전할 수 있어요'))}catch(e){notice('드래그 / 화살표로 시점을 움직이세요')}}
function resume(){paused=false;menu.classList.add('hidden');$('start').textContent='이어서 하기';canvas.focus();initAudio();lock()}
function pause(){if(paused)return;paused=true;shooting=false;aim=false;keys={};document.exitPointerLock?.();menu.classList.remove('hidden');$('start').textContent='이어서 하기';$('result').textContent='일시정지 · 총기를 바꾸려면 숫자 1~6';}
function finish(){ended=true;paused=true;shooting=false;document.exitPointerLock?.();menu.classList.remove('hidden');$('result').textContent=`${scores[0]===scores[1]?'무승부':scores[0]>scores[1]?'승리!':'패배 · 다시 도전하세요'} | 아군 ${scores[0]} : 적군 ${scores[1]}`;$('start').textContent='다시 시작'}
$('start').onclick=()=>{if(!started||ended)reset();else resume()};$('pause').onclick=pause;$('sound').onclick=()=>{muted=!muted;$('sound').textContent=muted?'🔇 소리 꺼짐':'🔊 소리 켜짐';initAudio()};
function changeGun(i){if(i===weaponIndex)return;weaponIndex=i;reload=0;cooldown=.25;notice(weapons[i].name)}
window.addEventListener('keydown',e=>{if(['KeyW','KeyA','KeyS','KeyD','ArrowLeft','ArrowRight','Space'].includes(e.code))e.preventDefault();if(e.code==='Escape'){pause();return}if(paused)return;keys[e.code]=true;if(e.code==='KeyR')doReload();if(/^Digit[1-6]$/.test(e.code))changeGun(Number(e.code.slice(-1))-1)});
window.addEventListener('keyup',e=>keys[e.code]=false);window.addEventListener('blur',pause);
document.addEventListener('visibilitychange',()=>{if(document.hidden)pause()});
canvas.addEventListener('contextmenu',e=>e.preventDefault());canvas.addEventListener('mousedown',e=>{if(paused)return;canvas.focus();drag=true;if(e.button===0){shooting=true;fire()}if(e.button===2)aim=true});window.addEventListener('mouseup',e=>{drag=false;if(e.button===0)shooting=false;if(e.button===2)aim=false});
window.addEventListener('mousemove',e=>{if(!paused&&(document.pointerLockElement===canvas||drag))player.a+=Math.max(-150,Math.min(150,e.movementX||0))*(aim?.0018:.003)});
document.addEventListener('pointerlockchange',()=>{if(document.pointerLockElement!==canvas&&started&&!paused)pause()});
function doReload(){if(!reload&&ammo[weaponIndex]<weapons[weaponIndex].mag&&death<=0){reload=weapons[weaponIndex].reload;notice('재장전 중…')}}
function fire(){if(paused||death>0||reload>0||cooldown>0)return;let w=weapons[weaponIndex];if(ammo[weaponIndex]<=0){doReload();return}ammo[weaponIndex]--;cooldown=w.rate;flash=.065;sound('shot',weaponIndex===1?.7:1);let a=player.a+(Math.random()-.5)*w.spread*(aim?.35:1),best=null,dist=Infinity;
for(let b of bots){if(b.team!==1||b.hp<=0)continue;let d=Math.hypot(b.x-player.x,b.y-player.y),error=Math.abs(angle(Math.atan2(b.y-player.y,b.x-player.x)-a));if(d<w.range&&error<Math.atan2(.3,d)&&d<dist&&visible(player,b)){best=b;dist=d}}
if(best){hit=.14;if(best.shield<=0){best.hp-=w.dmg;if(best.hp<=0)kill(best,0)}}
}
function kill(v,killer){if(v===player){if(death>0)return;death=3;player.hp=0;shooting=false}else{if(v.dead>0)return;v.hp=0;v.dead=3}scores[killer]++;if(scores[killer]>=limit)finish()}
// Breadth-first pathfinding around obstacles on the compact arena grid.
function pathTo(e,t){let sx=Math.floor(e.x),sy=Math.floor(e.y),tx=Math.floor(t.x),ty=Math.floor(t.y),q=[[sx,sy]],prev=new Map([[sx+','+sy,null]]);let cursor=0;
while(cursor<q.length){let [x,y]=q[cursor++];if(x===tx&&y===ty)break;for(let [dx,dy] of [[1,0],[-1,0],[0,1],[0,-1]]){let nx=x+dx,ny=y+dy,k=nx+','+ny;if(!wall(nx+.5,ny+.5)&&!prev.has(k)){prev.set(k,[x,y]);q.push([nx,ny])}}}
let p=[tx,ty],out=[];if(!prev.has(p.join(',')))return out;while(p&&!(p[0]===sx&&p[1]===sy)){out.push({x:p[0]+.5,y:p[1]+.5});p=prev.get(p.join(','))}return out.reverse()}
function update(dt){if(paused)return;total+=dt;remaining=Math.max(0,remaining-dt);cooldown-=dt;flash-=dt;hit-=dt;damageFlash-=dt;player.shield-=dt;noteTime-=dt;if(noteTime<=0)$('notice').textContent='';if(remaining<=0){finish();return}
if(reload>0){reload-=dt;if(reload<=0){ammo[weaponIndex]=weapons[weaponIndex].mag;notice('재장전 완료')}}
if(death>0){death-=dt;if(death<=0){Object.assign(player,spawn(0),{hp:100,shield:2});ammo=weapons.map(w=>w.mag);reload=0;notice('부활 · 2초 보호')}}else{
let forward=(keys.KeyW?1:0)-(keys.KeyS?1:0),side=(keys.KeyD?1:0)-(keys.KeyA?1:0),norm=Math.hypot(forward,side)||1;
let speed=(keys.ShiftLeft&&!aim?3.4:aim?1.5:2.4)*dt;
move(player,(Math.cos(player.a)*forward-Math.sin(player.a)*side)*speed/norm,(Math.sin(player.a)*forward+Math.cos(player.a)*side)*speed/norm);
if(keys.ArrowLeft)player.a-=dt*1.9;if(keys.ArrowRight)player.a+=dt*1.9;
if(forward||side){bob+=dt*(keys.ShiftLeft?13:9);step-=dt;if(step<=0){sound('step');step=keys.ShiftLeft?.28:.43}}else bob=0;
if(shooting&&weapons[weaponIndex].auto)fire();}
for(let b of bots){b.shield-=dt;if(b.dead>0){b.dead-=dt;if(b.dead<=0)Object.assign(b,spawn(b.team),{hp:100,shield:1.5,path:[],think:0});continue}if(b.hp<=0)continue;b.cool-=dt;b.think-=dt;let targets=bots.filter(t=>t.team!==b.team&&t.hp>0);if(b.team===1&&death<=0)targets.push(player);targets.sort((a,c)=>Math.hypot(a.x-b.x,a.y-b.y)-Math.hypot(c.x-b.x,c.y-b.y));let target=targets[0];if(!target)continue;let d=Math.hypot(target.x-b.x,target.y-b.y),los=visible(b,target);
if(los&&d<12){if(b.cool<=0){b.cool=.48+Math.random()*.35;if(d<9)sound('shot',.7,Math.max(.05,.25-d*.017));if(Math.random()<Math.max(.2,.68-d*.025)&&target.shield<=0){target.hp-=12+Math.random()*6;if(target===player){damageFlash=.16}if(target.hp<=0)kill(target,b.team)}}if(d>6)move(b,(target.x-b.x)/d*dt*1.2,(target.y-b.y)/d*dt*1.2)}else{if(b.think<=0){b.path=pathTo(b,target);b.think=.7+Math.random()*.5}let next=b.path[0];if(next){let dx=next.x-b.x,dy=next.y-b.y,dd=Math.hypot(dx,dy);if(dd<.15)b.path.shift();else move(b,dx/dd*dt*1.65,dy/dd*dt*1.65)}}
if(paused)break;
}}
function draw(){W=canvas.width;H=canvas.height;ctx.fillStyle='#819897';ctx.fillRect(0,0,W,H/2);let floor=ctx.createLinearGradient(0,H/2,0,H);floor.addColorStop(0,'#4b5552');floor.addColorStop(1,'#202927');ctx.fillStyle=floor;ctx.fillRect(0,H/2,W,H/2);if(!player)return;
let fov=aim?FOV*.62:FOV,proj=W/(2*Math.tan(fov/2)),z=[],strip=3;
for(let x=0;x<W;x+=strip){let offset=Math.atan((x-W/2)/proj),a=player.a+offset,d=ray(player.x,player.y,a),corrected=Math.max(.05,d*Math.cos(offset));z[Math.floor(x/strip)]=corrected;let h=proj/corrected,wx=player.x+Math.cos(a)*d,wy=player.y+Math.sin(a)*d,side=Math.min(wx%1,1-wx%1)<.06;let shade=Math.max(28,160-corrected*9)-(side?17:0);ctx.fillStyle=`rgb(${shade*.92},${shade},${shade*.95})`;ctx.fillRect(x,(H-h)/2,strip+1,h);ctx.fillStyle='#1119';if((Math.floor((wx+wy)*4)%4)===0)ctx.fillRect(x,(H-h)/2,strip+1,h);ctx.fillStyle='#b4c7a51c';ctx.fillRect(x,(H-h)/2,strip+1,Math.max(1,h*.025));}
let sprites=bots.filter(b=>b.hp>0).map(b=>({b,d:Math.hypot(b.x-player.x,b.y-player.y)})).sort((a,b)=>b.d-a.d);
for(let {b,d} of sprites){let a=angle(Math.atan2(b.y-player.y,b.x-player.x)-player.a);if(Math.abs(a)>fov*.9||d<.2)continue;let depth=d*Math.cos(a),sx=W/2+Math.tan(a)*proj,sh=proj/depth*.85,sw=sh*.48,top=H/2-sh*.43;let color=b.team===0?'#68c9c1':'#e28269';
for(let x=Math.max(0,Math.floor(sx-sw/2));x<Math.min(W,sx+sw/2);x+=2){if(depth>z[Math.min(z.length-1,Math.floor(x/strip))]+.1)continue;let u=(x-(sx-sw/2))/sw;ctx.fillStyle=color;if(u>.18&&u<.82)ctx.fillRect(x,top+sh*.23,2,sh*.42);ctx.fillStyle='#d6ba99';if(u>.31&&u<.69)ctx.fillRect(x,top,2,sh*.2);ctx.fillStyle='#253337';if((u>.2&&u<.43)||(u>.57&&u<.8))ctx.fillRect(x,top+sh*.65,2,sh*.35);ctx.fillStyle='#26332e';if(u>.55)ctx.fillRect(x,top+sh*.38,2,sh*.08)}
if(depth<z[Math.max(0,Math.min(z.length-1,Math.floor(sx/strip)))]+.1&&Math.abs(a)<fov/2){ctx.fillStyle=color;ctx.font=`bold ${Math.max(10,Math.min(15,sh*.13))}px sans-serif`;ctx.textAlign='center';ctx.fillText(b.team===0?'아군':'적군',sx,top-10);}}
// Procedurally drawn viewmodel, crosshair and muzzle flash.
let gun=weapons[weaponIndex],kick=flash>0?16:0,gx=aim?W*.5:W*.7,gy=H+Math.sin(bob)*5+(reload>0?70:0)+kick,scale=H/640;
ctx.save();ctx.translate(gx,gy);ctx.scale(scale,scale);ctx.fillStyle='#9f8669';ctx.beginPath();ctx.moveTo(-65,0);ctx.lineTo(-35,-130);ctx.lineTo(20,-120);ctx.lineTo(90,0);ctx.fill();ctx.fillStyle=gun.color;ctx.fillRect(-31,-210,62,155);ctx.fillStyle='#222c2d';ctx.fillRect(-16,-285,32,90);ctx.fillStyle='#15201f';ctx.fillRect(-23,-216,46,20);ctx.fillRect(-8,-300,16,24);ctx.fillStyle='#99ad96';ctx.fillRect(-3,-300,6,7);ctx.fillStyle='#172322';ctx.fillRect(-18,-160,36,62);if(weaponIndex===1){ctx.fillStyle='#acb5b3';ctx.fillRect(-38,-195,76,45)}if(flash>0){ctx.fillStyle='#ffe692';ctx.beginPath();ctx.moveTo(0,-350-Math.random()*30);ctx.lineTo(20,-307);ctx.lineTo(4,-285);ctx.lineTo(-24,-320);ctx.closePath();ctx.fill()}ctx.restore();
ctx.strokeStyle=hit>0?'#ffdb8a':'#e6f3d5';ctx.lineWidth=2;let cx=W/2,cy=H/2,gap=aim?4:9;ctx.beginPath();for(let [dx,dy] of [[1,0],[-1,0],[0,1],[0,-1]]){ctx.moveTo(cx+dx*gap,cy+dy*gap);ctx.lineTo(cx+dx*(gap+7),cy+dy*(gap+7))}ctx.stroke();if(hit>0){ctx.strokeStyle='#f9df8d';ctx.strokeRect(cx-12,cy-12,24,24)}if(damageFlash>0){ctx.fillStyle='#ed473d44';ctx.fillRect(0,0,W,H)}if(death>0){ctx.fillStyle='#121818aa';ctx.fillRect(0,0,W,H);ctx.fillStyle='white';ctx.textAlign='center';ctx.font='bold 26px sans-serif';ctx.fillText(`${Math.ceil(death)}초 후 부활`,W/2,H/2)}
// Minimap top-left, allies/enemies colored consistently.
let sz=5,mx=20,my=125;ctx.fillStyle='#071311bb';ctx.fillRect(mx-4,my-4,108,108);for(let y=0;y<20;y++)for(let x=0;x<20;x++){ctx.fillStyle=map[y][x]==='1'?'#657b6e':'#273b34';ctx.fillRect(mx+x*sz,my+y*sz,sz-1,sz-1)}for(let e of [player,...bots]){if(e.hp<=0)continue;ctx.fillStyle=e===player?'#edffaf':e.team===0?'#68c9c1':'#e28269';ctx.beginPath();ctx.arc(mx+e.x*sz,my+e.y*sz,2.4,0,TAU);ctx.fill()}
$('team').textContent=`아군 ${bots.filter(b=>b.team===0&&b.hp>0).length+(death<=0?1:0)} / 3 · 적군 ${bots.filter(b=>b.team===1&&b.hp>0).length} / 3`;
$('timer').textContent=`${Math.floor(remaining/60)}:${String(Math.floor(remaining%60)).padStart(2,'0')}`;$('score').textContent=`청록 ${scores[0]} : ${scores[1]} 주황 · ${limit}킬 승리`;$('health').textContent=`HP ${Math.max(0,Math.ceil(player.hp))}${player.shield>0?' · 부활 보호':''}`;$('ammo').textContent=`${gun.name} · ${reload>0?'재장전…':ammo[weaponIndex]+' / '+gun.mag} · 예비탄 무제한`;
}
function resize(){let r=canvas.getBoundingClientRect();canvas.width=Math.max(480,Math.min(1280,Math.round(r.width)));canvas.height=Math.round(r.height)}window.addEventListener('resize',resize);resize();
function frame(t){let dt=Math.min(.04,(t-last)/1000||.016);last=t;update(dt);draw();requestAnimationFrame(frame)}requestAnimationFrame(frame);
// Crossed AK-style / M16-style vector silhouettes; no external logo asset.
{let c=$('logo').getContext('2d');function rifle(rotation,wood){c.save();c.translate(260,128);c.rotate(rotation);c.fillStyle=wood?'#a87845':'#99aaa0';c.fillRect(-148,-15,215,30);c.fillStyle='#c1cec0';c.fillRect(50,-6,130,12);c.fillRect(160,-12,16,24);c.fillStyle='#344c40';c.fillRect(-22,13,23,51);c.fillStyle=wood?'#b18a57':'#718c7b';c.beginPath();c.moveTo(-143,-15);c.lineTo(-205,-30);c.lineTo(-205,30);c.lineTo(-143,15);c.fill();c.fillStyle='#7e9a81';c.fillRect(12,10,24,52);c.fillStyle='#e3efbe';c.fillRect(55,-18,20,10);c.restore()}rifle(-.52,true);rifle(.52,false);c.fillStyle='#dff3a8';c.font='bold 15px sans-serif';c.textAlign='center';c.fillText('AK 47  ×  M16',260,244)}
</script></body></html>'''

st.set_page_config(page_title='플레이 건 플', page_icon='🎮', layout='wide')
st.markdown('### 🎮 플레이 건 플')
st.caption('PC 브라우저용 3:3 FPS · 게임 화면 클릭 후 플레이 · ESC로 일시정지')
components.html(GAME, height=780, scrolling=False)
with st.expander('실행·배포 및 조작 안내'):
    st.markdown('''**배포:** GitHub 저장소 최상위에 `app.py`와 `requirements.txt`를 올린 뒤 Streamlit Community Cloud에서 시작 파일을 `app.py`로 지정하세요.

**로컬 실행:** `pip install -r requirements.txt` → `streamlit run app.py`

**조작:** WASD 이동, 마우스 시점, 좌클릭 발사, 우클릭 조준, R 재장전, 숫자 1~6 총기 교체, Shift 달리기, ESC 일시정지.

**규칙:** 플레이어와 아군 AI 2명 대 적군 AI 3명. 먼저 15킬 또는 3분 종료 시 높은 점수 팀 승리. 동점은 무승부. 사망 후 3초 뒤 부활합니다. 예비탄은 무제한입니다.

**지원:** 데스크톱 Chrome/Edge 권장. Streamlit 내장 화면의 마우스 잠금이 브라우저 정책으로 제한되면 드래그 또는 좌우 방향키로 시점을 바꾸세요. 사운드는 시작 버튼을 누른 뒤 활성화됩니다.

**구현 범위:** 완전한 3D 엔진 대신 2.5D 레이캐스팅으로 만든 1인칭 게임입니다. 외부 이미지·음원 없이 총기 실루엣, 적 캐릭터, 총성과 발소리를 프로그램으로 표현합니다. M16도 연사형으로 단순화했습니다. 로고는 AK47·M16을 모티브로 한 X자 실루엣이며 실물의 정밀 재현은 아닙니다. 멀티플레이·성적 저장·모바일 조작은 포함하지 않습니다.''')
