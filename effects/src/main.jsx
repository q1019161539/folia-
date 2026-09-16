import React,{useEffect,useMemo,useRef,useState} from "react";
import {createRoot} from "react-dom/client";
import {LyricPlayer} from "@applemusic-like-lyrics/react";
import "@applemusic-like-lyrics/core/style.css";
import "./style.css";

const initial={lines:[],currentMs:0,playing:false,effect:"amll-flow",fontSize:52,position:62,horizontal:50,width:84,lineSpacing:120,weight:800,glow:12,accent:"#ffffff",opacity:1};
function timedCharacters(line){
  if(["forced-character","corrected-character"].includes(line.timing_precision)&&Array.isArray(line.words)&&line.words.length){
    return line.words.map(item=>({word:String(item.text||""),startTime:Number(item.start_ms)||Number(line.start_ms)||0,endTime:Math.max(Number(item.start_ms)||0,Number(item.end_ms)||0),obscene:false,corrected:!!item.corrected,originalText:String(item.original_text||"")}));
  }
  const chars=Array.from(String(line.text||""));
  const start=Number(line.start_ms)||0,end=Math.max(start+1,Number(line.end_ms)||start+2500),unit=(end-start)/Math.max(1,chars.length);
  return chars.map((word,index)=>({word,startTime:Math.round(start+unit*index),endTime:Math.round(start+unit*(index+1)),obscene:false}));
}
function TimedText({line,time}){
  const timed=timedCharacters(line);
  return <span className="timed-text">{timed.map((item,index)=>{
    const start=Number(item.startTime)||0,end=Math.max(start+1,Number(item.endTime)||start+1),progress=Math.max(0,Math.min(100,(time-start)/(end-start)*100));
    return <span key={index} title={item.corrected?`ASR 原字：${item.originalText||"（漏字）"}；黄色仅预览`:undefined} className={`word-char ${time>=end?"passed":time>=start?"active":""} ${item.corrected?"corrected":""}`} style={{"--char-fill":`${progress}%`}}>{item.word}</span>;
  })}</span>;
}
function KineticLayer({state,time}){
  const rows=state.lines.filter(x=>!x.deleted&&x.text),index=rows.findIndex(x=>time>=x.start_ms&&time<x.end_ms),current=rows[index];
  if(!current)return <div className="kinetic empty-line">等待歌词时间轴</div>;
  const timed=timedCharacters(current);
  if(state.effect==="kinetic-bounce")return <div className="kinetic bounce"><div className="bounce-line" key={`${index}-${current.text}`}>{timed.map((item,i)=><span key={i} title={item.corrected?`ASR 原字：${item.originalText||"（漏字）"}；黄色仅预览`:undefined} className={`${time>=item.endTime?'passed':time>=item.startTime?'active':''} ${item.corrected?'corrected':''}`}>{item.word}</span>)}</div><small>{rows[index+1]?.text||""}</small></div>;
  if(state.effect==="kinetic-cinema")return <div className="kinetic cinema-lines"><small>{rows[index-1]?.text||""}</small><strong key={`${index}-${current.text}`}><TimedText line={current} time={time}/></strong><em>{rows[index+1]?.text||""}</em></div>;
  if(state.effect==="kinetic-neon")return <div className="kinetic neon"><strong key={`${index}-${current.text}`} data-text={current.text}><TimedText line={current} time={time}/></strong><small>{rows[index+1]?.text||""}</small></div>;
  return <div className="kinetic stack">{rows.slice(Math.max(0,index-2),index+3).map(line=><div key={`${line.start_ms}-${line.text}`} className={line===current?'active':''}>{line===current?<TimedText line={line} time={time}/>:line.text}</div>)}</div>;
}
function App(){
  const [state,setState]=useState(initial),[time,setTime]=useState(0),playerRef=useRef(null),metaRef=useRef("");
  const lyricLines=useMemo(()=>state.lines.filter(x=>!x.deleted&&x.text).map(x=>({startTime:Number(x.start_ms)||0,endTime:Number(x.end_ms)||Number(x.start_ms||0)+2500,translatedLyric:"",romanLyric:"",isBG:false,isDuet:state.effect==="amll-right",words:timedCharacters(x)})),[state.lines,state.effect]);
  useEffect(()=>{
    const receive=e=>{
      if(e.data?.type!=="folia-amll")return;
      const next={...initial,...e.data.payload};
      setTime(Math.round(next.currentMs||0));
      playerRef.current?.lyricPlayer?.setCurrentTime(Math.round(next.currentMs||0),!!next.seeking);
      const meta=JSON.stringify([next.lines,next.playing,next.effect,next.fontSize,next.position,next.horizontal,next.width,next.lineSpacing,next.weight,next.glow,next.accent,next.opacity]);
      if(meta!==metaRef.current){metaRef.current=meta;setState(next)}
    };
    addEventListener("message",receive);parent.postMessage({type:"folia-amll-ready"},"*");
    return()=>removeEventListener("message",receive);
  },[]);
  const focus=["amll-focus","amll-karaoke"].includes(state.effect),cinema=state.effect==="amll-cinema",karaoke=state.effect==="amll-karaoke";
  const vars={"--font-size":`${state.fontSize}px`,"--opacity":state.opacity,"--x":state.horizontal,"--y":state.position,"--width":state.width,"--line-spacing":state.lineSpacing/100,"--weight":state.weight,"--glow":`${state.glow}px`,"--accent":state.accent};
  if(state.effect.startsWith("kinetic-"))return <div className={`effect-root ${state.effect.replace("kinetic-","")}`} style={vars}><KineticLayer state={state} time={time}/></div>;
  return <div className={`effect-root ${state.effect.replace("amll-","")}`} style={vars}><LyricPlayer ref={playerRef} lyricLines={lyricLines} currentTime={time} playing={state.playing} alignAnchor={focus?"bottom":"center"} alignPosition={Math.max(.12,Math.min(.9,(state.position||62)/100))} enableSpring={!cinema} enableBlur={!focus} enableScale wordFadeWidth={karaoke ? .04 : cinema ? 1 : .55} hidePassedLines={focus}/></div>;
}
createRoot(document.getElementById("root")).render(<App/>);
