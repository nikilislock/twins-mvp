import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useLoader, useThree } from "@react-three/fiber";
import { OrbitControls, Html, Line } from "@react-three/drei";
import * as THREE from "three";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import { mergeVertices } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import { neutralPoseRad, segmentTransforms } from "./vendor/fk.js";
import type { State, XYZ } from "./types";
import { useLab } from "./state";

const ASSET="/static/assets/";
const shades=["#b5c8bf","#d2bda0"];
let flyPromise:Promise<any>|null=null;
function flyAssets(){
  if(!flyPromise)flyPromise=fetch(ASSET+"fly/model.json").then(r=>{if(!r.ok)throw new Error("Sinek geometrisi yüklenemedi");return r.json();}).then(async model=>{
    const loader=new STLLoader();
    const files=[...new Set(Object.values(model.meshes).map((v:any)=>v.file))] as string[];
    const raw=await Promise.all(files.map(file=>loader.loadAsync(ASSET+"fly/meshes/"+file)));
    const geometries:Record<string,THREE.BufferGeometry>={};
    model.segments.forEach((name:string)=>{
      const info=model.meshes[name];let g=raw[files.indexOf(info.file)].clone();
      g.scale(model.meshScale,model.meshScale*(info.mirror?-1:1),model.meshScale);
      if(info.mirror){const p=g.getAttribute("position");for(let i=0;i<p.count;i+=3){const a=new THREE.Vector3().fromBufferAttribute(p,i);const c=new THREE.Vector3().fromBufferAttribute(p,i+2);p.setXYZ(i,c.x,c.y,c.z);p.setXYZ(i+2,a.x,a.y,a.z);}}
      g.deleteAttribute("normal");g=mergeVertices(g,.003);g.computeVertexNormals();geometries[name]=g;
    });
    raw.forEach(g=>g.dispose());
    return {model,geometries};
  });
  return flyPromise;
}

export function Fly({index=0,macro=false,magnification=1}:{index?:number;macro?:boolean;magnification?:number}){
  const [asset,setAsset]=useState<any>(null);
  const group=useRef<THREE.Group>(null),rig=useRef<THREE.Group>(null),phase=useRef(0);
  const meshes=useRef<Record<string,THREE.Mesh>>({});
  useEffect(()=>{let live=true;flyAssets().then(a=>{if(live)setAsset(a);}).catch(e=>useLab.getState().notify(e.message));return()=>{live=false;};},[]);
  const pose=useMemo(()=>asset?neutralPoseRad(asset.model):{},[asset]);
  useFrame((_,dt)=>{
    const state=useLab.getState().state,body=state?.twins[index];if(!asset||!body||!group.current)return;
    if(!macro){
      group.current.position.lerp(new THREE.Vector3((body.x-.5)*18,.01,(body.y-.5)*18),Math.min(1,dt*9));
      group.current.rotation.y=THREE.MathUtils.damp(group.current.rotation.y,-body.heading,12,dt);
    }
    if(state?.running&&!useLab.getState().replay)phase.current+=dt*Math.min(12,(body.internal?.speed_mm_s||0)*.4);
    const next={...pose};
    ["lf","lm","lh","rf","rm","rh"].forEach((leg,j)=>{
      const wave=Math.sin(phase.current*5+([0,Math.PI,0,Math.PI,0,Math.PI][j]));
      next[`c_thorax-${leg}_coxa-pitch`]=(pose[`c_thorax-${leg}_coxa-pitch`]||0)+wave*.16;
      next[`${leg}_trochanterfemur-${leg}_tibia-pitch`]=(pose[`${leg}_trochanterfemur-${leg}_tibia-pitch`]||0)+Math.max(0,wave)*.22;
    });
    const transforms=segmentTransforms(asset.model,next);
    for(const name of asset.model.segments){const mesh=meshes.current[name];if(mesh){mesh.matrix.set(...transforms[name] as [number,number,number,number,number,number,number,number,number,number,number,number,number,number,number,number]);mesh.matrixWorldNeedsUpdate=true;}}
  });
  if(!asset)return null;
  return <group ref={group} position={macro?[0,0,0]:[((index?.64:.31)-.5)*18,0,0]} scale={macro?1:.10*magnification}>
    <group ref={rig} rotation={[-Math.PI/2,0,0]}>
      {asset.model.segments.map((name:string)=>{
        const eye=name.includes("eye"),wing=name.includes("wing"),leg=/coxa|tarsus|tibia|femur/.test(name);
        return <mesh key={name} ref={m=>{if(m)meshes.current[name]=m;}} geometry={asset.geometries[name]} matrixAutoUpdate={false} castShadow={!wing} receiveShadow>
          <meshStandardMaterial color={eye?"#773323":wing?"#d5d3c4":leg?"#5b4030":name.includes("abdomen")?"#74604a":"#967b51"} roughness={eye?.27:wing?.22:.63} metalness={wing?.08:0} side={THREE.DoubleSide} transparent={wing} opacity={wing?.32:1} depthWrite={!wing}/>
        </mesh>;
      })}
    </group>
  </group>;
}

function Mouse({macro=false}:{macro?:boolean}){
  const original=useLoader(STLLoader,ASSET+"mouse/mouse-body-ct.stl");
  const group=useRef<THREE.Group>(null);
  const geometry=useMemo(()=>{
    let g=original.clone();g.deleteAttribute("normal");g=mergeVertices(g,.04);g.computeVertexNormals();
    // Source CT uses its long axis along z; rotate into the arena's horizontal x.
    g.rotateY(Math.PI/2);g.computeBoundingBox();
    const b=g.boundingBox!;g.translate(-(b.min.x+b.max.x)/2,-b.min.y,-(b.min.z+b.max.z)/2);
    g.scale(.05,.05,.05);
    return g;
  },[original]);
  useFrame((_,dt)=>{
    const m=useLab.getState().state?.world?.mouse;if(!m||!group.current)return;
    group.current.visible=macro||m.enabled;
    if(!macro){
      group.current.position.lerp(new THREE.Vector3((m.x-.5)*18,.025,(m.y-.5)*18),Math.min(1,dt*7));
      let diff=THREE.MathUtils.euclideanModulo(-m.heading-group.current.rotation.y+Math.PI,2*Math.PI)-Math.PI;
      group.current.rotation.y+=diff*Math.min(1,dt*8);
    }
  });
  return <group ref={group}>
    <mesh geometry={geometry} castShadow receiveShadow><meshStandardMaterial color="#a7a299" roughness={.95}/></mesh>
  </group>;
}

function Label({at,text,color}:{at:XYZ;text:string;color:string}){
  return <Html position={at} center style={{pointerEvents:"none"}}><div className="specimen-label" style={{borderColor:color}}>{text}</div></Html>;
}

function Chamber({state,trails,fields,labels,magnification}:{state:State;trails:boolean;fields:boolean;labels:boolean;magnification:number}){
  const w=state.world;if(!w)return null;
  return <group>
    <mesh position={[0,-.28,0]} receiveShadow><boxGeometry args={[19,.55,19]}/><meshStandardMaterial color="#c2c0b7" roughness={.85}/></mesh>
    <mesh position={[0,-.005,0]} rotation={[-Math.PI/2,0,0]} receiveShadow><planeGeometry args={[18,18]}/><meshStandardMaterial color="#cbc9bf" roughness={.82}/></mesh>
    <gridHelper args={[18,18,"#9b9c95","#b6b6ad"]} position={[0,.004,0]}/>
    {[[0,-9.13,18.35,.22],[0,9.13,18.35,.22],[-9.13,0,.22,18.35],[9.13,0,.22,18.35]].map(([x,z,sx,sz],i)=><mesh key={i} position={[x,.22,z]} castShadow receiveShadow><boxGeometry args={[sx,.46,sz]}/><meshStandardMaterial color="#727b7b" metalness={.38} roughness={.48}/></mesh>)}
    {w.obstacles.map(o=><mesh key={o.id} position={[(o.x+o.w/2-.5)*18,o.height*9,(o.y+o.h/2-.5)*18]} castShadow receiveShadow><boxGeometry args={[o.w*18,o.height*18,o.h*18]}/><meshStandardMaterial color="#657576" roughness={.5} metalness={.18}/></mesh>)}
    {w.refuges.map(o=><group key={o.id} position={[(o.x+o.w/2-.5)*18,0,(o.y+o.h/2-.5)*18]}>
      <mesh position={[0,o.height*18,0]} castShadow><boxGeometry args={[o.w*18,.1,o.h*18]}/><meshStandardMaterial color="#8c9b8c" roughness={.7}/></mesh>
      {[-1,1].map(side=><mesh key={side} position={[side*o.w*8.7,o.height*9,0]} castShadow><boxGeometry args={[.09,o.height*18,o.h*18]}/><meshStandardMaterial color="#758571"/></mesh>)}
    </group>)}
    {w.food.map((f,i)=><group key={i} position={[(f.x-.5)*18,.065,(f.y-.5)*18]}>
      <mesh receiveShadow><cylinderGeometry args={[f.radius*18,f.radius*18,.12,40]}/><meshStandardMaterial color="#c4af83" roughness={.9}/></mesh>
      <mesh rotation={[Math.PI/2,0,0]}><torusGeometry args={[f.radius*18,.04,8,48]}/><meshStandardMaterial color="#ece7d7" roughness={.4}/></mesh>
    </group>)}
    {fields&&w.heat_zones.map((z,i)=><mesh key={i} position={[(z.x-.5)*18,.014,(z.y-.5)*18]} rotation={[-Math.PI/2,0,0]}><circleGeometry args={[z.radius*18,48]}/><meshBasicMaterial color="#b46943" transparent opacity={.32} depthWrite={false}/></mesh>)}
    <Fly index={0} magnification={magnification}/><Fly index={1} magnification={magnification}/><Suspense fallback={null}><Mouse/></Suspense>
    {state.twins.map((t,i)=><group key={t.id}>
      {labels&&<Label at={[(t.x-.5)*18,.75,(t.y-.5)*18]} text={`FLY ${t.id}`} color={shades[i]}/>}
      {trails&&t.trail?.length>1&&<Line points={t.trail.map(p=>[(p.x-.5)*18,.04,(p.y-.5)*18] as XYZ)} color={i?"#9e724e":"#456e62"} lineWidth={1.5} transparent opacity={.55}/>}
      {fields&&w.observations[i]?.predator_visible&&w.mouse.enabled&&<Line points={[[(t.x-.5)*18,.17,(t.y-.5)*18],[(w.mouse.x-.5)*18,.6,(w.mouse.y-.5)*18]]} color="#a46b46" lineWidth={1} dashed dashSize={.16} gapSize={.12}/>}
    </group>)}
    {labels&&w.mouse.enabled&&<Label at={[(w.mouse.x-.5)*18,2.25,(w.mouse.y-.5)*18]} text={`MOUSE / ${w.mouse.state.toUpperCase()}`} color="#bdb5a8"/>}
    {trails&&w.mouse.trail.length>1&&<Line points={w.mouse.trail.map(p=>[(p.x-.5)*18,.035,(p.y-.5)*18] as XYZ)} color="#92766e" lineWidth={1} transparent opacity={.35}/>}
  </group>;
}

function CameraRig({view,macro=false}:{view:string;macro?:boolean}){
  const controls=useRef<any>(null);const {camera}=useThree();
  useEffect(()=>{
    const c=controls.current;if(!c)return;
    if(macro){camera.position.set(5,3.5,6);c.target.set(0,.65,0);}
    else if(view==="top"){camera.position.set(0,23,.001);c.target.set(0,0,0);}
    else if(view==="free"){camera.position.set(13,15,17);c.target.set(0,0,0);}
    else{camera.position.set(3,3.5,4);}
    c.update();
  },[view,macro,camera]);
  useFrame((_,dt)=>{
    if(macro||view==="free"||view==="top"||!controls.current)return;
    const s=useLab.getState().state;
    const b=view==="mouse"?s?.world?.mouse:s?.twins[view==="b"?1:0];if(!b)return;
    const target=new THREE.Vector3((b.x-.5)*18,view==="mouse"?.6:.15,(b.y-.5)*18);
    const delta=target.clone().sub(controls.current.target).multiplyScalar(Math.min(1,dt*5));
    controls.current.target.add(delta);camera.position.add(delta);
  });
  return <OrbitControls ref={controls} makeDefault enableDamping dampingFactor={.12} minDistance={macro?2:.35} maxDistance={macro?18:42} maxPolarAngle={Math.PI*.485}/>;
}

export function WorldScene({view="free",trails=true,fields=false,labels=true,magnification=2.5,macro}:{view?:string;trails?:boolean;fields?:boolean;labels?:boolean;magnification?:number;macro?:number|"mouse"}){
  const state=useLab(s=>s.state);
  return <Canvas shadows dpr={[1,1.7]} camera={{position:[13,15,17],fov:40,near:.02,far:100}} gl={{antialias:true,powerPreference:"high-performance"}} onCreated={({gl})=>{gl.setClearColor("#222729");gl.toneMapping=THREE.ACESFilmicToneMapping;gl.toneMappingExposure=1.15;}}>
    <ambientLight intensity={.6}/><hemisphereLight args={["#fff8e9","#6b777d",2.1]}/>
    <directionalLight position={[4,14,6]} intensity={3.1} castShadow shadow-mapSize={[2048,2048]} shadow-camera-left={-13} shadow-camera-right={13} shadow-camera-top={13} shadow-camera-bottom={-13} shadow-normalBias={.03}/>
    <directionalLight position={[-7,4,-8]} intensity={1.3} color="#d4e0e5"/>
    {macro!==undefined?<><mesh rotation={[-Math.PI/2,0,0]} receiveShadow><planeGeometry args={[200,200]}/><meshStandardMaterial color="#333a3d" roughness={.9}/></mesh><Suspense fallback={null}>{macro==="mouse"?<Mouse macro/>:<Fly index={macro} macro/>}</Suspense></>:state&&<Chamber state={state} trails={trails} fields={fields} labels={labels} magnification={magnification}/>}
    <CameraRig view={view} macro={macro!==undefined}/>
  </Canvas>;
}
