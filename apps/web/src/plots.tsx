import {useEffect,useRef} from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import type {Telemetry} from "./types";
export function Trace({data,variable,title,unit="",height=156}:{data:Telemetry[];variable:string;title:string;unit?:string;height?:number}){
  const ref=useRef<HTMLDivElement>(null),plot=useRef<uPlot|null>(null);
  const latest=useRef(data);latest.current=data;
  const series=()=>[latest.current.map(d=>d.seconds),...["a","b"].map(s=>latest.current.map(d=>typeof (d as any)[s]?.[variable]==="number"?(d as any)[s][variable]:null))] as uPlot.AlignedData;
  useEffect(()=>{
    if(!ref.current)return;
    const p=new uPlot({width:Math.max(120,ref.current.clientWidth),height,
      padding:[12,12,0,0],legend:{show:false},
      scales:{x:{time:false}},cursor:{drag:{x:false,y:false}},
      series:[{label:"Süre",value:(_,v)=>v==null?"—":v.toFixed(2)+" s"},{label:"Fly A",stroke:"#a9c4b8",width:1.4},{label:"Fly B",stroke:"#c8a87d",width:1.4}],
      axes:[{stroke:"#899295",grid:{stroke:"#333a3d",width:1},ticks:{stroke:"#333a3d"},font:"11px Segoe UI",size:28,values:(_,vals)=>vals.map(v=>v+"s")},
            {stroke:"#899295",grid:{stroke:"#2b3235",width:1},ticks:{stroke:"#333a3d"},font:"11px Segoe UI",size:42,values:(_,vals)=>vals.map(v=>Number(v.toPrecision(3)).toString())}],
    },series(),ref.current);plot.current=p;
    const observer=new ResizeObserver(()=>{if(ref.current)p.setSize({width:Math.max(120,ref.current.clientWidth),height});});observer.observe(ref.current);
    return()=>{observer.disconnect();p.destroy();plot.current=null;};
  },[variable,height]);
  useEffect(()=>{plot.current?.setData(series());},[data]);
  return <section className="trace"><div className="trace-title"><span>{title}</span><span>{unit}</span></div><div ref={ref}/>{data.length===0&&<span className="no-samples">Kayıt bekleniyor</span>}</section>;
}
