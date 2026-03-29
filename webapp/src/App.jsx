import { useState, useEffect } from "react";
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell, ReferenceLine, Legend, PieChart, Pie } from "recharts";
import { fetchDays, fetchStats, fetchProfile, updateProfile, fetchRecommendations } from "./api";

// ═══════════════════════════════════════
// CONSTANTS
// ═══════════════════════════════════════
const PLAN = { kcal: 1500, p: 110, f: 55, c: 141 };
const PLAN_TDEE = 2000;
const C = {
  bg: "#0a0a0f", card: "#141419", border: "#252530", text: "#e8e8ed", dim: "#8888a0",
  accent: "#6366f1", accentL: "#818cf8", green: "#22c55e", red: "#ef4444", orange: "#f59e0b",
  cyan: "#06b6d4", purple: "#a855f7", protein: "#3b82f6", fat: "#f59e0b", carbs: "#22c55e",
};
const PAGES = [
  { id: "day", label: "День", icon: "📅" },
  { id: "stats", label: "Стат", icon: "📊" },
  { id: "analysis", label: "Анализ", icon: "🔬" },
  { id: "profile", label: "Профиль", icon: "👤" },
];
const fmt = (n) => (n >= 0 ? `+${n}` : `${n}`);

// ═══════════════════════════════════════
// MAIN
// ═══════════════════════════════════════
export default function App() {
  const [page, setPage] = useState("day");
  const [monthData, setMonthData] = useState(null);
  const [cumulative, setCumulative] = useState(null);
  const [profile, setProfile] = useState({
    weight: 80, height: 172, bf: 25, muscle: 33, age: 23,
    tdee_base: 2000, plan_kcal: 1500, targets: { ...PLAN },
  });
  const [selectedDay, setSelectedDay] = useState(null);
  const [loading, setLoading] = useState(true);
  const [statsRange, setStatsRange] = useState("all");
  const [editingProfile, setEditingProfile] = useState(false);

  const dayKeys = monthData?.days ? Object.keys(monthData.days).map(Number).sort((a, b) => a - b) : [];

  useEffect(() => {
    (async () => {
      try {
        const [daysResp, statsResp, profileResp] = await Promise.all([
          fetchDays().catch(() => ({ days: {} })),
          fetchStats().catch(() => ({ balance: 0, days_tracked: 0, start_date: "" })),
          fetchProfile().catch(() => null),
        ]);

        const md = daysResp || { days: {} };
        const cum = statsResp || { balance: 0, days_tracked: 0, start_date: "" };

        setMonthData(md);
        setCumulative(cum);
        if (profileResp) setProfile(profileResp);

        const keys = md?.days ? Object.keys(md.days).map(Number).sort((a, b) => a - b) : [];
        setSelectedDay(keys.length > 0 ? keys[keys.length - 1] : null);
      } catch (e) {
        console.error("Load error:", e);
        setMonthData({ days: {} });
        setCumulative({ balance: 0, days_tracked: 0, start_date: "" });
      }
      setLoading(false);
    })();
  }, []);

  const currentDay = selectedDay != null ? monthData?.days?.[selectedDay.toString()] : null;
  const dayIdx = dayKeys.indexOf(selectedDay);
  const canPrev = dayIdx > 0;
  const canNext = dayIdx >= 0 && dayIdx < dayKeys.length - 1;
  const nav = (dir) => { const ni = dayIdx + dir; if (ni >= 0 && ni < dayKeys.length) setSelectedDay(dayKeys[ni]); };

  const getStats = () => {
    if (!monthData?.days) return [];
    let keys = [...dayKeys];
    if (statsRange === "week") keys = keys.slice(-7);
    if (statsRange === "2weeks") keys = keys.slice(-14);
    let cb = 0;
    return keys.map(d => { const day = monthData.days[d.toString()]; cb += day.balance; return { date: `${d}`, eaten: day.totals.kcal, tdee: day.tdee, balance: day.balance, cumBalance: cb, p: day.totals.p, f: day.totals.f, c: day.totals.c }; });
  };

  const getAnalysis = () => {
    if (!monthData?.days) return { topMeals: [], avgMacros: {}, dayCount: 0 };
    const mc = {}; let tP=0, tF=0, tC=0, tK=0, dc=0;
    Object.values(monthData.days).forEach(day => {
      dc++; tP += day.totals.p; tF += day.totals.f; tC += day.totals.c; tK += day.totals.kcal;
      day.meals.forEach(m => { const k = m.id||m.name; if(!mc[k]) mc[k]={name:m.name,count:0,kcal:m.kcal,p:m.p,f:m.f,c:m.c}; mc[k].count++; });
    });
    return { topMeals: Object.values(mc).sort((a,b)=>b.count-a.count).slice(0,12), avgMacros: { p:Math.round(tP/dc), f:Math.round(tF/dc), c:Math.round(tC/dc), kcal:Math.round(tK/dc) }, dayCount: dc };
  };

  if (loading) return (
    <div style={{ background: C.bg, height: "100vh", display: "flex", alignItems: "center", justifyContent: "center", color: C.text, fontFamily: "'JetBrains Mono', monospace" }}>
      <div style={{ textAlign: "center" }}><div style={{ fontSize: 32, marginBottom: 12 }}>⚡</div><div style={{ color: C.dim }}>Загрузка...</div></div>
    </div>
  );

  return (
    <div style={{ background: C.bg, minHeight: "100vh", color: C.text, fontFamily: "'JetBrains Mono','SF Mono',monospace", fontSize: 13, paddingBottom: 70 }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&display=swap');
        *{box-sizing:border-box;margin:0;padding:0}
        @keyframes slideUp{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
        .cd{background:${C.card};border:1px solid ${C.border};border-radius:10px;padding:16px;margin-bottom:10px;animation:slideUp .3s ease}
        .btn{padding:8px 16px;border-radius:8px;border:1px solid ${C.border};background:${C.card};color:${C.text};cursor:pointer;font-family:inherit;font-size:12px;transition:all .15s}
        .btn:hover{border-color:${C.accent};background:${C.accent}22}
        .btn:disabled{opacity:.25;cursor:default}
        .btn:disabled:hover{border-color:${C.border};background:${C.card}}
        .btn-a{border-color:${C.accent};background:${C.accent}22;color:${C.accentL}}
        .inp{padding:8px 12px;border-radius:6px;border:1px solid ${C.border};background:${C.bg};color:${C.text};font-family:inherit;font-size:13px;width:100%}
        .inp:focus{outline:none;border-color:${C.accent}}
        .ds::-webkit-scrollbar{height:0;width:0}
      `}</style>

      <div style={{ padding:"16px 16px 10px", borderBottom:`1px solid ${C.border}`, display:"flex", justifyContent:"space-between", alignItems:"center" }}>
        <div>
          <div style={{ fontSize:16, fontWeight:700, letterSpacing:"-0.5px" }}>⚡ NUTRITION</div>
          <div style={{ fontSize:11, color:C.dim, marginTop:2 }}>{cumulative ? `${cumulative.days_tracked}д · ${fmt(cumulative.balance)} ккал` : "—"}</div>
        </div>
      </div>

      <div style={{ padding:"12px 16px" }}>
        {page==="day" && <DayPage data={currentDay} day={selectedDay} onNav={nav} canPrev={canPrev} canNext={canNext} dayKeys={dayKeys} onSelect={setSelectedDay} profile={profile} />}
        {page==="stats" && <StatsPage data={getStats()} range={statsRange} setRange={setStatsRange} cumulative={cumulative} />}
        {page==="analysis" && <AnalysisPage data={getAnalysis()} profile={profile} />}
        {page==="profile" && <ProfilePage profile={profile} setProfile={setProfile} editing={editingProfile} setEditing={setEditingProfile} />}
      </div>

      <div style={{ position:"fixed",bottom:0,left:0,right:0,background:`${C.bg}ee`,backdropFilter:"blur(10px)",borderTop:`1px solid ${C.border}`,display:"flex",justifyContent:"space-around",padding:"8px 0 12px" }}>
        {PAGES.map(p => (
          <button key={p.id} onClick={()=>setPage(p.id)} style={{ background:"none",border:"none",color:page===p.id?C.accent:C.dim,cursor:"pointer",textAlign:"center",fontFamily:"inherit",fontSize:10,padding:"4px 12px" }}>
            <div style={{ fontSize:18,marginBottom:2 }}>{p.icon}</div>{p.label}
          </button>
        ))}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════
// DAY PAGE
// ═══════════════════════════════════════
function DayPage({ data, day, onNav, canPrev, canNext, dayKeys, onSelect, profile }) {
  const BMR = 1666;
  const NEAT = PLAN_TDEE - BMR;

  const tg = profile.targets || PLAN;

  const Strip = () => (
    <div className="ds" style={{ display:"flex", gap:4, overflowX:"auto", marginBottom:12, paddingBottom:4 }}>
      {dayKeys.map(d => (
        <button key={d} onClick={()=>onSelect(d)} style={{
          minWidth:36, height:36, borderRadius:8, border:`1px solid ${d===day?C.accent:C.border}`,
          background:d===day?`${C.accent}22`:C.card, color:d===day?C.accentL:C.dim,
          cursor:"pointer", fontFamily:"inherit", fontSize:12, fontWeight:d===day?700:400, flexShrink:0, transition:"all .15s",
        }}>{d}</button>
      ))}
    </div>
  );

  if (dayKeys.length === 0) return (
    <div className="cd" style={{ textAlign:"center",padding:40,color:C.dim }}>
      <div style={{ fontSize:36,marginBottom:12 }}>🍽</div>
      <div style={{ fontSize:14,fontWeight:600,color:C.text,marginBottom:8 }}>Нет данных</div>
      <div style={{ fontSize:12,lineHeight:1.5 }}>Начни трекать еду в чате.<br/>При закрытии дня данные появятся здесь.</div>
    </div>
  );

  if (!data) return (<div><Strip /><div className="cd" style={{ textAlign:"center",padding:40,color:C.dim }}><div style={{ fontSize:28,marginBottom:8 }}>📭</div>Нет данных за этот день</div></div>);

  const { meals, activities, totals, tdee, balance } = data;
  const bCol = balance<=0 ? C.green : C.red;
  const actBonus = activities.reduce((s, a) => s + a.kcal, 0);

  // Group meals
  const grouped = {}; const order = ["Завтрак","Обед","Перекус","Ужин"];
  meals.forEach(m => { const t=m.meal||"Другое"; if(!grouped[t]) grouped[t]=[]; grouped[t].push(m); });
  const sorted = order.filter(t=>grouped[t]).map(t=>[t,grouped[t]]);
  Object.keys(grouped).filter(t=>!order.includes(t)).forEach(t=>sorted.push([t,grouped[t]]));

  const MB = ({label,value,target,color}) => {
    const pct=Math.min((value/target)*100,100); const over=value>target*1.1;
    return (<div style={{marginBottom:10}}>
      <div style={{display:"flex",justifyContent:"space-between",marginBottom:4}}>
        <span style={{color:C.dim,fontSize:11}}>{label}</span>
        <span style={{fontWeight:600,color:over?C.red:C.text,fontSize:12}}>{value}<span style={{color:C.dim,fontWeight:400}}>/{target}г</span></span>
      </div>
      <div style={{height:6,background:C.bg,borderRadius:3,overflow:"hidden"}}>
        <div style={{height:"100%",width:`${pct}%`,background:over?C.red:color,borderRadius:3,transition:"width .4s ease"}} />
      </div>
    </div>);
  };

  const ERow = ({label, value, sub, color, bold}) => (
    <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"7px 0",borderBottom:`1px solid ${C.border}`}}>
      <div>
        <div style={{fontSize:12,color:bold?C.text:C.dim,fontWeight:bold?600:400}}>{label}</div>
        {sub && <div style={{fontSize:10,color:C.dim,marginTop:1}}>{sub}</div>}
      </div>
      <div style={{fontWeight:bold?700:600,fontSize:bold?16:13,color:color||C.text}}>{value}</div>
    </div>
  );

  return (
    <div>
      <Strip />

      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:12}}>
        <button className="btn" onClick={()=>onNav(-1)} disabled={!canPrev} style={{padding:"6px 12px"}}>←</button>
        <div style={{textAlign:"center"}}>
          <div style={{fontSize:18,fontWeight:700}}>День {day}</div>
        </div>
        <button className="btn" onClick={()=>onNav(1)} disabled={!canNext} style={{padding:"6px 12px"}}>→</button>
      </div>

      <div className="cd" style={{textAlign:"center",padding:20}}>
        <div style={{color:C.dim,fontSize:10,fontWeight:600,letterSpacing:1,marginBottom:6}}>⚡ ЭНЕРГЕТИЧЕСКИЙ БАЛАНС</div>
        <div style={{fontSize:32,fontWeight:700,color:bCol,lineHeight:1}}>{fmt(balance)}</div>
        <div style={{fontSize:11,color:C.dim,marginTop:6}}>{totals.kcal} съедено − {tdee} потрачено</div>
      </div>

      <div className="cd">
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:12}}>
          <div style={{fontSize:11,color:C.dim,fontWeight:600,letterSpacing:1}}>🍽 СЪЕДЕНО</div>
          <div style={{fontSize:18,fontWeight:700}}>{totals.kcal} <span style={{fontSize:11,color:C.dim,fontWeight:400}}>/ {tg.kcal} ккал</span></div>
        </div>
        <div style={{height:8,background:C.bg,borderRadius:4,overflow:"hidden",marginBottom:16}}>
          <div style={{height:"100%",width:`${Math.min((totals.kcal/tg.kcal)*100,100)}%`,background:totals.kcal>tg.kcal?C.red:C.accent,borderRadius:4,transition:"width .4s"}} />
        </div>

        <div style={{fontSize:11,color:C.dim,fontWeight:600,letterSpacing:1,marginBottom:10}}>НУТРИЕНТЫ</div>
        <MB label="Белок" value={totals.p} target={tg.p} color={C.protein} />
        <MB label="Жиры" value={totals.f} target={tg.f} color={C.fat} />
        <MB label="Углеводы" value={totals.c} target={tg.c} color={C.carbs} />
      </div>

      {sorted.map(([type,items]) => (
        <div key={type} className="cd">
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:8}}>
            <div style={{fontSize:11,color:C.accentL,fontWeight:600,letterSpacing:1}}>{type.toUpperCase()}</div>
            <div style={{fontSize:11,color:C.dim}}>{items.reduce((s,m)=>s+m.kcal,0)} ккал</div>
          </div>
          {items.map((m,i) => (
            <div key={i} style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"7px 0",borderBottom:i<items.length-1?`1px solid ${C.border}`:"none"}}>
              <div style={{flex:1,minWidth:0}}>
                <div style={{fontSize:12,lineHeight:1.3,wordBreak:"break-word"}}>{m.name}</div>
                <div style={{fontSize:10,color:C.dim,marginTop:2}}>Б{m.p} · Ж{m.f} · У{m.c}</div>
              </div>
              <div style={{fontWeight:600,fontSize:14,minWidth:50,textAlign:"right",flexShrink:0}}>{m.kcal}</div>
            </div>
          ))}
        </div>
      ))}

      <div className="cd">
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:12}}>
          <div style={{fontSize:11,color:C.dim,fontWeight:600,letterSpacing:1}}>🔥 РАСХОД ЭНЕРГИИ</div>
          <div style={{fontSize:18,fontWeight:700}}>{tdee} <span style={{fontSize:11,color:C.dim,fontWeight:400}}>ккал</span></div>
        </div>

        <ERow label="Базовый метаболизм (BMR)" sub="Энергия на поддержание жизни в покое" value={`${BMR}`} />
        <ERow label="Бытовая активность" sub="Ходьба по дому, работа сидя (×1.2)" value={`+${NEAT}`} color={C.dim} />

        {activities.length > 0 ? (
          <>
            <div style={{fontSize:10,color:C.accentL,fontWeight:600,letterSpacing:1,marginTop:10,marginBottom:4}}>ДОПОЛНИТЕЛЬНАЯ АКТИВНОСТЬ</div>
            {activities.map((a, i) => (
              <div key={i} style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"7px 0",borderBottom:`1px solid ${C.border}`}}>
                <div>
                  <div style={{fontSize:12}}>{a.name}</div>
                  <div style={{fontSize:10,color:C.dim,marginTop:1}}>
                    {a.duration}{a.category ? ` · ${a.category}` : ""}
                  </div>
                </div>
                <div style={{fontWeight:600,fontSize:13,color:C.orange}}>+{a.kcal}</div>
              </div>
            ))}
          </>
        ) : (
          <div style={{padding:"8px 0",color:C.dim,fontSize:12,fontStyle:"italic"}}>Без дополнительной активности</div>
        )}

        <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"10px 0 0",marginTop:4}}>
          <div style={{fontSize:12,fontWeight:600}}>Итого TDEE</div>
          <div style={{fontSize:16,fontWeight:700}}>{tdee}</div>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════
// STATS PAGE
// ═══════════════════════════════════════
function StatsPage({ data, range, setRange, cumulative }) {
  if (!data.length) return <div className="cd" style={{textAlign:"center",color:C.dim,padding:40}}>Нет данных</div>;
  const avgBal=Math.round(data.reduce((s,d)=>s+d.balance,0)/data.length);
  const totalBal=data.reduce((s,d)=>s+d.balance,0);
  const fatKg=(Math.abs(totalBal)/7700).toFixed(2);
  const Tip=({active,payload,label})=>{if(!active||!payload?.length)return null;return(<div style={{background:C.card,border:`1px solid ${C.border}`,borderRadius:6,padding:"8px 12px",fontSize:11}}><div style={{fontWeight:600,marginBottom:4}}>{label}</div>{payload.map((p,i)=><div key={i} style={{color:p.color,marginBottom:2}}>{p.name}: {p.value}</div>)}</div>);};

  return (
    <div>
      <div style={{display:"flex",gap:6,marginBottom:12}}>
        {[["week","7д"],["2weeks","14д"],["all","Всё"]].map(([id,label])=>(<button key={id} className={`btn ${range===id?"btn-a":""}`} onClick={()=>setRange(id)}>{label}</button>))}
      </div>

      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8,marginBottom:12}}>
        <div className="cd" style={{textAlign:"center"}}><div style={{color:C.dim,fontSize:10,marginBottom:4}}>СР. БАЛАНС/ДЕНЬ</div><div style={{fontSize:20,fontWeight:700,color:avgBal<=0?C.green:C.red}}>{fmt(avgBal)}</div></div>
        <div className="cd" style={{textAlign:"center"}}><div style={{color:C.dim,fontSize:10,marginBottom:4}}>ИТОГО</div><div style={{fontSize:20,fontWeight:700,color:totalBal<=0?C.green:C.red}}>{fmt(totalBal)}</div><div style={{fontSize:10,color:C.dim}}>≈ {totalBal<=0?"-":"+"}{fatKg} кг</div></div>
      </div>

      <div className="cd">
        <div style={{fontSize:11,color:C.dim,fontWeight:600,marginBottom:12,letterSpacing:1}}>БАЛАНС ПО ДНЯМ</div>
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={data}><CartesianGrid strokeDasharray="3 3" stroke={C.border}/><XAxis dataKey="date" tick={{fill:C.dim,fontSize:10}} axisLine={{stroke:C.border}}/><YAxis tick={{fill:C.dim,fontSize:10}} axisLine={{stroke:C.border}}/><Tooltip content={<Tip/>}/><ReferenceLine y={0} stroke={C.dim} strokeDasharray="3 3"/><Bar dataKey="balance" name="Баланс" radius={[3,3,0,0]}>{data.map((d,i)=><Cell key={i} fill={d.balance<=0?C.green:C.red} fillOpacity={0.8}/>)}</Bar></BarChart>
        </ResponsiveContainer>
      </div>

      <div className="cd">
        <div style={{fontSize:11,color:C.dim,fontWeight:600,marginBottom:12,letterSpacing:1}}>КУМУЛЯТИВНЫЙ БАЛАНС</div>
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={data}><CartesianGrid strokeDasharray="3 3" stroke={C.border}/><XAxis dataKey="date" tick={{fill:C.dim,fontSize:10}} axisLine={{stroke:C.border}}/><YAxis tick={{fill:C.dim,fontSize:10}} axisLine={{stroke:C.border}}/><Tooltip content={<Tip/>}/><ReferenceLine y={0} stroke={C.dim} strokeDasharray="3 3"/><Line type="monotone" dataKey="cumBalance" name="Кумулятивный" stroke={C.accent} strokeWidth={2} dot={{r:3,fill:C.accent}}/></LineChart>
        </ResponsiveContainer>
      </div>

      <div className="cd">
        <div style={{fontSize:11,color:C.dim,fontWeight:600,marginBottom:12,letterSpacing:1}}>НУТРИЕНТЫ: ФАКТ vs ПЛАН</div>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={[{name:"Белок",fact:Math.round(data.reduce((s,d)=>s+d.p,0)/data.length),plan:PLAN.p},{name:"Жиры",fact:Math.round(data.reduce((s,d)=>s+d.f,0)/data.length),plan:PLAN.f},{name:"Углев",fact:Math.round(data.reduce((s,d)=>s+d.c,0)/data.length),plan:PLAN.c}]}>
            <CartesianGrid strokeDasharray="3 3" stroke={C.border}/><XAxis dataKey="name" tick={{fill:C.dim,fontSize:11}} axisLine={{stroke:C.border}}/><YAxis tick={{fill:C.dim,fontSize:10}} axisLine={{stroke:C.border}}/><Tooltip content={<Tip/>}/>
            <Bar dataKey="fact" name="Факт" fill={C.accent} radius={[3,3,0,0]}/><Bar dataKey="plan" name="План" fill={C.border} radius={[3,3,0,0]}/><Legend wrapperStyle={{fontSize:11,color:C.dim}}/>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="cd">
        <div style={{fontSize:11,color:C.dim,fontWeight:600,marginBottom:10,letterSpacing:1}}>ИСТОРИЯ</div>
        <div style={{overflowX:"auto"}}>
          <table style={{width:"100%",borderCollapse:"collapse",fontSize:11}}>
            <thead><tr style={{borderBottom:`1px solid ${C.border}`}}>{["День","Съел","TDEE","±","Б","Ж","У"].map(h=>(<th key={h} style={{padding:"6px 3px",textAlign:"right",color:C.dim,fontWeight:500}}>{h}</th>))}</tr></thead>
            <tbody>{data.map((d,i)=>(<tr key={i} style={{borderBottom:`1px solid ${C.border}`}}>
              <td style={{padding:"6px 3px",color:C.accentL}}>{d.date}</td>
              <td style={{padding:"6px 3px",textAlign:"right"}}>{d.eaten}</td>
              <td style={{padding:"6px 3px",textAlign:"right",color:C.dim}}>{d.tdee}</td>
              <td style={{padding:"6px 3px",textAlign:"right",fontWeight:600,color:d.balance<=0?C.green:C.red}}>{fmt(d.balance)}</td>
              <td style={{padding:"6px 3px",textAlign:"right",color:d.p>=PLAN.p*0.9?C.text:C.red}}>{d.p}</td>
              <td style={{padding:"6px 3px",textAlign:"right",color:d.f<=PLAN.f*1.1?C.text:C.orange}}>{d.f}</td>
              <td style={{padding:"6px 3px",textAlign:"right"}}>{d.c}</td>
            </tr>))}</tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════
// ANALYSIS PAGE
// ═══════════════════════════════════════
function AnalysisPage({ data, profile }) {
  const {topMeals,avgMacros,dayCount}=data;
  const tg=profile.targets||PLAN;
  const [recs, setRecs]=useState(null);
  const [recsLoading, setRecsLoading]=useState(false);

  const loadRecs=async()=>{
    setRecsLoading(true);
    try { const r=await fetchRecommendations(); setRecs(r); } catch(e){ setRecs([]); }
    setRecsLoading(false);
  };

  useEffect(()=>{ if(dayCount>0) loadRecs(); },[dayCount]);

  if(!dayCount) return <div className="cd" style={{textAlign:"center",color:C.dim,padding:40}}>Нет данных</div>;
  const pR=((avgMacros.p*4)/avgMacros.kcal*100).toFixed(0);
  const fR=((avgMacros.f*9)/avgMacros.kcal*100).toFixed(0);
  const cR=((avgMacros.c*4)/avgMacros.kcal*100).toFixed(0);
  const pie=[{name:"Белок",value:+pR,fill:C.protein},{name:"Жиры",value:+fR,fill:C.fat},{name:"Углеводы",value:+cR,fill:C.carbs}];

  const recColor=(t)=>t==="warn"?C.orange:t==="ok"?C.green:C.cyan;

  return (
    <div>
      <div className="cd">
        <div style={{fontSize:11,color:C.dim,fontWeight:600,marginBottom:12,letterSpacing:1}}>РАСПРЕДЕЛЕНИЕ НУТРИЕНТОВ</div>
        <div style={{display:"flex",alignItems:"center",gap:16}}>
          <ResponsiveContainer width={120} height={120}><PieChart><Pie data={pie} dataKey="value" innerRadius={35} outerRadius={55} paddingAngle={2} startAngle={90} endAngle={-270}>{pie.map((d,i)=><Cell key={i} fill={d.fill}/>)}</Pie></PieChart></ResponsiveContainer>
          <div>{pie.map(d=>(<div key={d.name} style={{display:"flex",alignItems:"center",gap:8,marginBottom:6}}><div style={{width:10,height:10,borderRadius:2,background:d.fill}}/><span style={{fontSize:12}}>{d.name}: <b>{d.value}%</b></span></div>))}<div style={{fontSize:11,color:C.dim,marginTop:4}}>~{avgMacros.kcal} ккал/день</div></div>
        </div>
      </div>

      <div className="cd">
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:10}}>
          <div style={{fontSize:11,color:C.dim,fontWeight:600,letterSpacing:1}}>🤖 AI-РЕКОМЕНДАЦИИ</div>
          {recs && <button className="btn" onClick={loadRecs} style={{fontSize:10,padding:"4px 10px"}} disabled={recsLoading}>🔄</button>}
        </div>
        {recsLoading && <div style={{textAlign:"center",color:C.dim,fontSize:12,padding:16}}>Анализирую данные...</div>}
        {recs && recs.length>0 && recs.map((x,i)=>(<div key={i} style={{padding:"8px 10px",marginBottom:6,borderRadius:6,fontSize:12,background:`${recColor(x.type)}15`,borderLeft:`3px solid ${recColor(x.type)}`}}><b style={{color:C.text}}>{x.title}:</b> {x.text}</div>))}
        {recs && recs.length===0 && <div style={{color:C.dim,fontSize:12}}>Не удалось загрузить рекомендации</div>}
      </div>

      <div className="cd">
        <div style={{fontSize:11,color:C.dim,fontWeight:600,marginBottom:10,letterSpacing:1}}>🏆 ЧАСТЫЕ БЛЮДА ({dayCount}д)</div>
        {topMeals.map((m,i)=>(<div key={i} style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"7px 0",borderBottom:i<topMeals.length-1?`1px solid ${C.border}`:"none"}}>
          <div style={{display:"flex",alignItems:"center",gap:8,flex:1,minWidth:0}}>
            <span style={{color:C.dim,fontWeight:600,width:20,fontSize:11,flexShrink:0}}>#{i+1}</span>
            <div style={{minWidth:0}}><div style={{fontSize:12,lineHeight:1.3,wordBreak:"break-word"}}>{m.name}</div><div style={{fontSize:10,color:C.dim,marginTop:1}}>{m.kcal} ккал · Б{m.p} Ж{m.f} У{m.c}</div></div>
          </div>
          <span style={{padding:"3px 8px",borderRadius:4,fontSize:11,fontWeight:500,background:`${C.accent}22`,color:C.accentL,flexShrink:0}}>{m.count}×</span>
        </div>))}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════
// PROFILE PAGE
// ═══════════════════════════════════════
function ProfilePage({ profile, setProfile, editing, setEditing }) {
  const [form, setForm] = useState({...profile});
  useEffect(()=>{setForm({...profile})},[profile]);

  const save = async () => {
    const lm=form.weight*(1-form.bf/100); const bmr=Math.round(370+21.6*lm); const tdee=Math.round(bmr*1.2); const plan=tdee-500;
    const p=Math.round(form.weight*1.4); const f=Math.round(form.weight*0.7); const c=Math.round((plan-p*4-f*9)/4);
    const u={...form,tdee_base:tdee,plan_kcal:plan,targets:{kcal:plan,p,f,c}};
    setProfile(u); setEditing(false);
    try { await updateProfile(u); } catch(e) { console.error("Profile save error:", e); }
  };

  const fields=[{key:"weight",label:"Вес, кг"},{key:"height",label:"Рост, см"},{key:"age",label:"Возраст"},{key:"bf",label:"% жира"},{key:"muscle",label:"Мышцы, кг"}];
  const lm=profile.weight*(1-profile.bf/100); const bmr=Math.round(370+21.6*lm); const tg=profile.targets||PLAN;

  return (
    <div>
      <div className="cd">
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:12}}>
          <div style={{fontSize:11,color:C.dim,fontWeight:600,letterSpacing:1}}>ПАРАМЕТРЫ</div>
          <button className="btn" onClick={()=>editing?save():setEditing(true)} style={{fontSize:11}}>{editing?"💾 Сохранить":"✏️ Изменить"}</button>
        </div>
        {fields.map(f=>(<div key={f.key} style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"8px 0",borderBottom:`1px solid ${C.border}`}}>
          <span style={{color:C.dim,fontSize:12}}>{f.label}</span>
          {editing?<input className="inp" type="number" value={form[f.key]} onChange={e=>setForm({...form,[f.key]:+e.target.value})} style={{width:80,textAlign:"right"}}/>:<span style={{fontWeight:600}}>{profile[f.key]}</span>}
        </div>))}
      </div>

      <div className="cd">
        <div style={{fontSize:11,color:C.dim,fontWeight:600,marginBottom:10,letterSpacing:1}}>РАСЧЁТ</div>
        {[["Сухая масса",`${lm.toFixed(1)} кг`],["BMR",`${bmr} ккал`],["TDEE (×1.2)",`${profile.tdee_base} ккал`],["План (−500)",`${profile.plan_kcal||tg.kcal} ккал`]].map(([l,v])=>(
          <div key={l} style={{display:"flex",justifyContent:"space-between",padding:"6px 0",borderBottom:`1px solid ${C.border}`}}><span style={{color:C.dim,fontSize:12}}>{l}</span><span style={{fontWeight:600}}>{v}</span></div>
        ))}
      </div>

      <div className="cd">
        <div style={{fontSize:11,color:C.dim,fontWeight:600,marginBottom:10,letterSpacing:1}}>🎯 НУТРИЕНТЫ</div>
        {[["Калории",`${tg.kcal} ккал`],["Белок",`${tg.p} г`],["Жиры",`${tg.f} г`],["Углеводы",`${tg.c} г`]].map(([l,v])=>(
          <div key={l} style={{display:"flex",justifyContent:"space-between",padding:"6px 0",borderBottom:`1px solid ${C.border}`}}><span style={{color:C.dim,fontSize:12}}>{l}</span><span style={{fontWeight:600,color:C.accentL}}>{v}</span></div>
        ))}
      </div>

      <div className="cd" style={{textAlign:"center"}}>
        <div style={{fontSize:14,fontWeight:600}}>🎯 Жиросжигание ~2 кг/мес</div>
        <div style={{fontSize:11,color:C.dim,marginTop:4}}>Дефицит 500 ккал/день · Сохранение мышц</div>
      </div>
    </div>
  );
}
