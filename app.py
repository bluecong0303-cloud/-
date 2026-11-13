"""구름 카트: Python 3.10+ / streamlit run app.py.
GitHub 루트에 app.py, requirements.txt 업로드 후 Streamlit Cloud 배포.
외부 CDN, 이미지, 음원, 키 없이 동작하는 Canvas 유사 3D 레이싱.
"""
import streamlit as st
import streamlit.components.v1 as components

GAME = r'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
*{box-sizing:border-box}html,body{margin:0;background:#132838;font-family:system-ui,sans-serif;color:white}#wrap{position:relative;height:740px;width:100%;overflow:hidden;border-radius:18px}canvas{width:100%;height:100%;display:block;outline:none}.overlay{position:absolute;inset:0;background:#102b41df;display:flex;align-items:center;justify-content:center;z-index:5}.card{width:min(660px,94%);padding:30px;border:1px solid #ffffff66;border-radius:26px;background:linear-gradient(140deg,#234f6b,#153844);text-align:center}h1{font-size:clamp(38px,6vw,64px);margin:4px;color:#fff4b4}.tag{letter-spacing:4px;color:#84e9dc;font-size:12px}.logo{font-size:72px}p{line-height:1.8;color:#d9eaf0}button,select{border:0;border-radius:12px;padding:12px 22px;margin:5px;background:#defc82;color:#163840;font-weight:800;cursor:pointer;font-size:15px}select{background:#d7edf2}#hud{position:absolute;left:18px;right:18px;top:18px;display:flex;justify-content:space-between;pointer-events:none;text-shadow:0 2px 4px #000;font-weight:800}#bottom{position:absolute;left:18px;right:18px;bottom:20px;display:flex;align-items:end;justify-content:space-between;pointer-events:none;text-shadow:0 2px 4px #000}#speed{font-size:40px}#msg{position:absolute;top:24%;width:100%;text-align:center;font-size:38px;font-weight:900;color:#fff5b6;text-shadow:0 2px 5px #000;pointer-events:none}#tools{position:absolute;right:10px;top:68px;z-index:3}#tools button{font-size:12px;display:block;padding:8px;background:#153c55b0;color:white}.meter{width:170px;height:13px;border:1px solid white;border-radius:8px;overflow:hidden;margin-top:5px}.fill{height:100%;background:#a5f7d0}.hidden{display:none!important}.small{font-size:13px}
</style></head><body><div id="wrap"><canvas id="view" tabindex="0" aria-label="구름 카트 경주 화면"></canvas><div id="hud"><span id="rank">1 / 6</span><span id="lap">LAP 1 / 3</span><span id="clock">00:00.00</span></div><div id="tools"><button id="pause">⏸ 일시정지</button><button id="mute">🔊 소리 켜짐</button></div><div id="msg"></div><div id="bottom"><span><b id="speed">0</b> km/h<br><span id="status">READY</span></span><span>DRIFT ENERGY<div class="meter"><div class="fill" id="energy"></div></div><span id="boost">부스터 0 / 3</span></span></div><div class="overlay" id="menu"><div class="card"><div class="logo">☁️ 🏎️</div><div class="tag">CLOUD KART · COAST CIRCUIT</div><h1>구름 카트</h1><p>바닷바람을 가르며 코너를 미끄러져 보세요.<br>나 + AI 5명 · 3바퀴 · 드리프트로 부스터 충전!</p><select id="color" aria-label="카트 색상"><option value="#f2bb50">레몬 옐로</option><option value="#69dfd2">민트 블루</option><option value="#f28aaa">체리 핑크</option></select><button id="start">레이스 시작</button><p class="small">↑ / W 가속 · ↓ / S 브레이크 · ← → / A D 조향<br>Shift + 조향: 드리프트 · Space: 부스터 · ESC / P: 일시정지<br>게임 화면을 클릭한 뒤 조작하세요. PC 키보드 전용입니다.</p><p class="small" id="result">오리지널 캐릭터·트랙의 캐주얼 유사 3D 레이싱</p><button id="restart" class="hidden">처음부터 다시</button></div></div></div><script>
'use strict';
const $=id=>document.getElementById(id),canvas=$('view'),ctx=canvas.getContext('2d');
const SEG=200,ROAD=1800,DRAW=150,CAM=1000,DEPTH=.85,LAPS=3,MAX=11000;
const colors=['#70cad2','#e887a7','#a3a0ee','#f6a66f','#b1d966'];
let track=[],length=0,player,bots=[],keys={},started=false,paused=true,ended=false,countdown=3,time=0,last=0,energy=0,boosts=0,boostLeft=0,bump=0,note='',noteLeft=0,drifting=false,muted=false,audio=null,engine=null,engineGain=null,chosen='#f2bb50',seed=431;
function rng(){seed=(seed*1664525+1013904223)>>>0;return seed/4294967296}
function makeTrack(){track=[];let sections=[[50,0],[60,.9],[35,0],[75,-1.2],[45,.6],[40,0],[70,1.35],[40,-.5],[65,-.8],[40,0]];for(let [n,c] of sections)for(let i=0;i<n;i++){let ease=Math.sin(Math.PI*i/(n-1));track.push({i:track.length,curve:c*ease})}length=track.length*SEG}
makeTrack();
function wrap(v,m){return ((v%m)+m)%m}
function fmt(t){let m=Math.floor(t/60),s=Math.floor(t%60),h=Math.floor((t%1)*100);return `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}.${String(h).padStart(2,'0')}`}
function currentLap(distance){return Math.min(LAPS,Math.floor(distance/length)+1)}
function ranking(){return [player,...bots].sort((a,b)=>b.distance-a.distance).indexOf(player)+1}
function unlockAudio(){if(!audio){const A=window.AudioContext||window.webkitAudioContext;if(!A)return;audio=new A();engine=audio.createOscillator();engineGain=audio.createGain();engine.type='sawtooth';engineGain.gain.value=0;engine.connect(engineGain);engineGain.connect(audio.destination);engine.start()}audio.resume().catch(()=>{})}
function tone(freq,len=.15,vol=.08){if(!audio||muted)return;let o=audio.createOscillator(),g=audio.createGain();o.frequency.value=freq;g.gain.setValueAtTime(vol,audio.currentTime);g.gain.exponentialRampToValueAtTime(.001,audio.currentTime+len);o.connect(g);g.connect(audio.destination);o.start();o.stop(audio.currentTime+len);o.onended=()=>{o.disconnect();g.disconnect()}}
function tell(t){note=t;noteLeft=1.8}
function reset(){seed=431;chosen=$('color').value;player={distance:0,x:0,speed:0,color:chosen};bots=Array.from({length:5},(_,i)=>({distance:-300-i*350,x:(i%3-1)*.58,target:0,speed:MAX*(.72+i*.035),color:colors[i],phase:rng()*6,hit:0}));keys={};energy=0;boosts=0;boostLeft=0;bump=0;time=0;countdown=3;noteLeft=0;drifting=false;ended=false;started=true;resume()}
function resume(){paused=false;$('menu').classList.add('hidden');canvas.focus();unlockAudio()}
function pause(){if(paused||!started||ended)return;paused=true;keys={};$('menu').classList.remove('hidden');$('start').textContent='이어서 달리기';$('result').textContent='일시정지 · 기록은 그대로 유지됩니다.';$('restart').classList.remove('hidden');if(engineGain)engineGain.gain.value=0}
function finish(){ended=true;paused=true;keys={};$('menu').classList.remove('hidden');$('start').textContent='한 번 더 달리기';$('restart').classList.add('hidden');let rank=ranking();$('result').textContent=`완주! ${rank}위 / 6명 · 기록 ${fmt(time)}`;if(engineGain)engineGain.gain.value=0;tone(rank===1?880:660,.5)}
$('start').onclick=()=>{if(!started||ended)reset();else resume()};$('restart').onclick=reset;$('pause').onclick=pause;$('mute').onclick=()=>{muted=!muted;$('mute').textContent=muted?'🔇 소리 꺼짐':'🔊 소리 켜짐';if(engineGain)engineGain.gain.value=0};canvas.onclick=()=>canvas.focus();
window.addEventListener('keydown',e=>{if(['ArrowUp','ArrowDown','ArrowLeft','ArrowRight','Space','ShiftLeft','ShiftRight'].includes(e.code))e.preventDefault();if(['Escape','KeyP'].includes(e.code)){if(!e.repeat)pause();return}if(paused)return;keys[e.code]=true;if(e.code==='Space'&&!e.repeat&&boosts>0&&boostLeft<=0&&countdown<=0){boosts--;boostLeft=2.1;tell('BOOST!');tone(750,.25)}});
window.addEventListener('keyup',e=>keys[e.code]=false);window.addEventListener('blur',pause);document.addEventListener('visibilitychange',()=>{if(document.hidden)pause()});
function update(dt){if(paused)return;noteLeft=Math.max(0,noteLeft-dt);bump=Math.max(0,bump-dt);if(countdown>0){let old=Math.ceil(countdown);countdown-=dt;if(Math.ceil(countdown)!==old)tone(countdown>0?440:880,.16);return}
time+=dt;boostLeft=Math.max(0,boostLeft-dt);let seg=track[Math.floor(wrap(player.distance,length)/SEG)],turn=(keys.ArrowRight||keys.KeyD?1:0)-(keys.ArrowLeft||keys.KeyA?1:0),gas=keys.ArrowUp||keys.KeyW,brake=keys.ArrowDown||keys.KeyS;
drifting=!!(keys.ShiftLeft||keys.ShiftRight)&&turn!==0&&player.speed>MAX*.4&&Math.abs(player.x)<1.05;
let cap=boostLeft>0?MAX*1.35:MAX;if(gas||boostLeft>0)player.speed+=dt*(boostLeft>0?9000:4200);else player.speed-=dt*2000;if(brake)player.speed-=dt*8500;if(drifting)player.speed-=dt*950;
if(Math.abs(player.x)>1.05){player.speed-=dt*6500;if(player.speed>MAX*.55)tell('잔디에서는 속도가 줄어들어요')}
player.speed=Math.max(0,Math.min(cap,player.speed));let ratio=player.speed/MAX;
player.x+=turn*dt*(drifting?1.65:1.2)*Math.max(.15,ratio)-seg.curve*dt*ratio*ratio*.78;
player.x=Math.max(-1.8,Math.min(1.8,player.x));player.distance+=player.speed*dt;
if(drifting){energy+=dt*(22+Math.min(1,Math.abs(seg.curve))*14);if(energy>=100){if(boosts<3){boosts++;tone(1100,.13);tell('부스터 충전 완료!')}energy-=100}}
for(let [i,b] of bots.entries()){let c=track[Math.floor(wrap(b.distance,length)/SEG)].curve;let pace=MAX*(.73+i*.035)*(1-Math.abs(c)*.1);b.speed+=(pace-b.speed)*Math.min(1,dt*2);b.distance+=b.speed*dt;b.x=Math.sin(time*.3+b.phase)*.58;b.hit=Math.max(0,b.hit-dt);if(Math.abs(b.distance-player.distance)<200&&Math.abs(b.x-player.x)<.22&&bump<=0&&b.hit<=0){player.speed*=.68;b.speed*=.82;bump=.9;b.hit=1;tell('쿵! 다른 카트를 조심하세요');tone(110,.12)}}
if(engine&&engineGain){engine.frequency.setTargetAtTime(55+ratio*145,audio.currentTime,.08);engineGain.gain.setTargetAtTime(muted?0:.018,audio.currentTime,.05)}
if(player.distance>=length*LAPS)finish();
}
function poly(points,color){ctx.fillStyle=color;ctx.beginPath();points.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.closePath();ctx.fill()}
function kart(x,y,s,color,steer=0,drift=false){ctx.save();ctx.translate(x,y);ctx.scale(s,s);ctx.rotate(steer*.05);ctx.fillStyle='#0005';ctx.beginPath();ctx.ellipse(0,-3,65,18,0,0,Math.PI*2);ctx.fill();ctx.fillStyle='#1a2931';ctx.fillRect(-60,-44,21,43);ctx.fillRect(39,-44,21,43);ctx.fillRect(-48,-93,15,28);ctx.fillRect(33,-93,15,28);poly([[-47,-18],[-48,-67],[-30,-98],[30,-98],[48,-67],[47,-18]],color);ctx.fillStyle='#f4f9d2';ctx.fillRect(-30,-41,60,14);ctx.fillStyle='#29465a';ctx.fillRect(-29,-88,58,30);ctx.fillStyle='#fff0bd';ctx.beginPath();ctx.arc(0,-111,23,0,Math.PI*2);ctx.fill();ctx.fillStyle=color;ctx.beginPath();ctx.arc(0,-118,24,Math.PI,Math.PI*2);ctx.lineTo(24,-111);ctx.lineTo(-24,-111);ctx.fill();ctx.fillStyle='#204454';ctx.fillRect(-19,-119,38,12);ctx.fillStyle='#fff8';ctx.fillRect(-13,-117,11,3);ctx.fillStyle='#fdf4ce';ctx.fillRect(-41,-35,9,9);ctx.fillRect(32,-35,9,9);if(drift){for(let side of [-1,1]){ctx.fillStyle='#b2f2eeaa';for(let k=0;k<3;k++){ctx.beginPath();ctx.arc(side*(54+k*10),-9+k*12,9+k*4,0,Math.PI*2);ctx.fill()}}}ctx.restore()}
function render(){const W=canvas.width,H=canvas.height;let sky=ctx.createLinearGradient(0,0,0,H*.65);sky.addColorStop(0,'#6ebadc');sky.addColorStop(1,'#d5f3ed');ctx.fillStyle=sky;ctx.fillRect(0,0,W,H);ctx.fillStyle='#fff6ce';ctx.beginPath();ctx.arc(W*.8,H*.16,34,0,Math.PI*2);ctx.fill();for(let i=0;i<5;i++){let x=wrap(i*W*.3-time*4,W+200)-100;ctx.fillStyle='#ffffffad';ctx.beginPath();ctx.ellipse(x,H*.13+(i%2)*35,64,17,0,0,Math.PI*2);ctx.fill()}poly([[0,H*.45],[W*.13,H*.23],[W*.3,H*.43],[W*.48,H*.28],[W*.7,H*.45],[W,H*.29],[W,H*.6],[0,H*.6]],'#70b8a7');ctx.fillStyle='#51aeb3';ctx.fillRect(0,H*.44,W,H*.25);ctx.fillStyle='#8bbd72';ctx.fillRect(0,H*.57,W,H*.43);
if(!player){kart(W*.5,H*.87,1.5,'#f2bb50');return}
let position=wrap(player.distance,length),base=Math.floor(position/SEG),frac=(position%SEG)/SEG,curve=0,dx=0,rows=[],clip=H;
function project(z,x){let s=DEPTH/z;return {x:W/2+s*(x-player.x*ROAD)*W/2,y:H/2+s*CAM*H/2,w:s*ROAD*W/2,s}}
for(let n=1;n<DRAW;n++){let seg=track[(base+n)%track.length],z=(n-frac)*SEG;let near=project(z,curve);curve+=dx;dx+=seg.curve*34;let far=project(z+SEG,curve);rows.push({near,far,seg,n,clip});if(far.y<clip)clip=far.y}
// Far-to-near painter's order draws the road and all roadside objects.
for(let i=rows.length-1;i>=0;i--){let {near:a,far:b,seg,n}=rows[i];if(b.y>=H||a.y<0)continue;let alt=Math.floor(seg.i/3)%2===0;ctx.fillStyle=alt?'#8fc67b':'#89bf75';ctx.fillRect(0,b.y,W,Math.max(0,a.y-b.y+1));poly([[a.x-a.w*1.13,a.y],[a.x+a.w*1.13,a.y],[b.x+b.w*1.13,b.y],[b.x-b.w*1.13,b.y]],alt?'#f4eee0':'#ef8b75');poly([[a.x-a.w,a.y],[a.x+a.w,a.y],[b.x+b.w,b.y],[b.x-b.w,b.y]],alt?'#657b86':'#617680');
if(alt)for(let lane of [-1/3,1/3])poly([[a.x+a.w*lane-a.w*.012,a.y],[a.x+a.w*lane+a.w*.012,a.y],[b.x+b.w*lane+b.w*.012,b.y],[b.x+b.w*lane-b.w*.012,b.y]],'#eff3d3');
if(seg.i<3){for(let j=0;j<10;j++)poly([[a.x-a.w+j*a.w*.2,a.y],[a.x-a.w+(j+1)*a.w*.2,a.y],[b.x-b.w+(j+1)*b.w*.2,b.y],[b.x-b.w+j*b.w*.2,b.y]],(j+seg.i)%2?'#243d4b':'#fff4dc')}
if(seg.i%8===0&&n>3){for(let side of [-1,1]){let x=b.x+side*b.w*1.6,h=b.s*W*170;ctx.fillStyle='#8c7153';ctx.fillRect(x-h*.08,b.y-h*.6,h*.16,h*.6);poly([[x,b.y-h*1.6],[x-h*.45,b.y-h*.45],[x+h*.45,b.y-h*.45]],side===1?'#398c70':'#47a07b')}}
for(let bot of bots){let bd=wrap(bot.distance-player.distance,length),bn=Math.floor((bd+position%SEG)/SEG);if(bn===n){let f=(bd+position%SEG)/SEG-n,x=a.x+(b.x-a.x)*f,w=a.w+(b.w-a.w)*f,y=a.y+(b.y-a.y)*f;kart(x+bot.x*w,y,w/ROAD*8,bot.color)}}
}
let steer=(keys.ArrowRight||keys.KeyD?1:0)-(keys.ArrowLeft||keys.KeyA?1:0);if(boostLeft>0){ctx.strokeStyle='#f3ffaf88';ctx.lineWidth=3;for(let i=0;i<12;i++){let ang=i/12*Math.PI*2;ctx.beginPath();ctx.moveTo(W/2+Math.cos(ang)*W*.35,H/2+Math.sin(ang)*H*.35);ctx.lineTo(W/2+Math.cos(ang)*W*.6,H/2+Math.sin(ang)*H*.6);ctx.stroke()}}
if(drifting){ctx.strokeStyle='#263e4a66';ctx.lineWidth=9;for(let s of [-1,1]){ctx.beginPath();ctx.moveTo(W/2+s*54,H*.91);ctx.lineTo(W/2+s*58-steer*65,H);ctx.stroke()}}
kart(W*.5+steer*12,H*.91+Math.sin(time*22)*(player.speed/MAX)*2,Math.min(W/700,1.6),chosen,steer*(drifting?3:1),drifting);
// Track minimap, computed from integrated curvature for a stylized circuit overview.
ctx.fillStyle='#173e4bc9';ctx.fillRect(18,75,112,115);ctx.strokeStyle='#c1e1bc';ctx.lineWidth=7;ctx.beginPath();ctx.ellipse(74,130,38,40,0,0,Math.PI*2);ctx.stroke();for(let e of [...bots,player]){let a=wrap(e.distance,length)/length*Math.PI*2-Math.PI/2;ctx.fillStyle=e===player?'#fff39b':e.color;ctx.beginPath();ctx.arc(74+Math.cos(a)*38,130+Math.sin(a)*40,e===player?5:3,0,Math.PI*2);ctx.fill()}
$('rank').textContent=`${ranking()}위 / 6명`;$('lap').textContent=`LAP ${currentLap(player.distance)} / ${LAPS}`;$('clock').textContent=fmt(time);$('speed').textContent=Math.round(player.speed/MAX*180);$('status').textContent=boostLeft>0?'BOOST 🔥':drifting?'DRIFT ✨':Math.abs(player.x)>1.05?'잔디 감속':'COAST CIRCUIT';$('energy').style.width=energy+'%';$('boost').textContent=`부스터 ${boosts} / 3 · SPACE`;$('msg').textContent=countdown>0?String(Math.ceil(countdown)):time<.7?'GO!':noteLeft>0?note:'';
}
function resize(){let r=canvas.getBoundingClientRect();canvas.width=Math.max(480,Math.min(1280,Math.round(r.width)));canvas.height=Math.round(r.height)}window.addEventListener('resize',resize);resize();
function loop(t){let dt=Math.min(.04,(t-last)/1000||.016);last=t;update(dt);render();requestAnimationFrame(loop)}requestAnimationFrame(loop);
</script></body></html>'''

st.set_page_config(page_title='구름 카트', page_icon='🏎️', layout='wide')
st.markdown('### ☁️ 구름 카트')
st.caption('오리지널 캐주얼 레이싱 · AI 5명과 3바퀴 경주 · 게임 화면 클릭 후 키보드로 조작하세요.')
components.html(GAME, height=760, scrolling=False)
with st.expander('조작 · 실행 · 게임 안내'):
    st.markdown('''**GitHub 배포:** 저장소 최상위에 `app.py`, `requirements.txt`를 올리고 Streamlit Community Cloud에서 `app.py`를 시작 파일로 선택하세요.

**로컬 실행:** `pip install -r requirements.txt` 후 `streamlit run app.py`.

**조작:** ↑/W 가속 · ↓/S 브레이크 · ←→/AD 조향 · Shift+조향 드리프트 · Space 부스터 · ESC/P 일시정지. 게임 화면을 먼저 클릭하세요.

**게임:** 플레이어와 AI 5명의 3바퀴 레이스입니다. 드리프트 중 게이지가 차면 부스터가 생기며 최대 3개 보관합니다. 부스터는 약 2초간 작동합니다. 잔디에서는 감속하고 카트와 부딪혀도 속도가 줄어듭니다. 완주 순간 누적 주행거리로 순위를 계산합니다.

**참고:** 카트라이더의 캐주얼 주행 느낌에서 착안한 독자적인 게임으로, 원작 캐릭터·로고·맵·음원은 사용하지 않았습니다. 실사 3D 엔진이 아닌 Canvas 기반 유사 3D 도로 투영입니다. 엔진음과 효과음은 합성 사운드이며 시작 버튼 이후 재생됩니다. 미니맵은 실제 코스 모양이 아닌 진행도를 표시하는 타원형 도식입니다. 아이템전·온라인 멀티플레이·모바일 조작·기록 영구 저장은 포함하지 않습니다. PC Chrome/Edge를 권장합니다.''')
