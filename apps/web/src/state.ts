import { create } from "zustand";
import type { State } from "./types";
export const useLab = create<{state:State|null;connected:boolean;busy:boolean;replay:boolean;notice:string;setState:(s:State)=>void;notify:(s:string)=>void}>((set)=>({
  state:null,connected:false,busy:false,replay:false,notice:"",
  setState:(state)=>set({state,connected:true}),
  notify:(notice)=>{set({notice});setTimeout(()=>set({notice:""}),6500);}
}));
export async function api<T=any>(path:string,body?:unknown):Promise<T>{
  const result=await fetch(path,{method:body===undefined?"GET":"POST",headers:body===undefined?{}:{"Content-Type":"application/json"},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(60000)});
  if(!result.ok){let detail;try{detail=(await result.json()).detail;}catch{}throw new Error(typeof detail==="string"?detail:`İşlem başarısız (${result.status})`);}
  return result.json();
}
export async function control(action:string,value?:unknown,extra:object={}){
  if(useLab.getState().busy||useLab.getState().replay)return;
  useLab.setState({busy:true});
  try{useLab.getState().setState(await api<State>("/api/control",{action,value,...extra}));}
  catch(e){useLab.getState().notify((e as Error).message);}
  finally{useLab.setState({busy:false});}
}
let polling=false;
export function startPolling(){
  if(polling)return;polling=true;let disposed=false;
  async function next(){if(disposed)return;
    if(!useLab.getState().busy&&!useLab.getState().replay){
      try{const s=await api<State>("/api/state");if(!useLab.getState().busy&&!useLab.getState().replay)useLab.getState().setState(s);}
      catch{useLab.setState({connected:false});}
    }setTimeout(next,450);
  }next();return()=>{disposed=true;polling=false;};
}
export const fmt=(x:unknown,d=2)=>typeof x==="number"&&Number.isFinite(x)?x.toLocaleString("tr-TR",{maximumFractionDigits:d,minimumFractionDigits:d}):"—";
export const count=(x:unknown)=>fmt(x,0);
