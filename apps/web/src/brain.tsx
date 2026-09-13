import { useEffect, useMemo, useRef } from "react";
import { Canvas, useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { OrbitControls, Line, Html } from "@react-three/drei";
import * as THREE from "three";
import type { Activity, AtlasData, XYZ } from "./types";

const palette=["#c8bda7","#96b8b2","#ccab83","#b5bbaa","#92a5af","#bba397","#d0c5af","#76959a","#a7a8b3","#b5b1a0"];

function BrainPoints({atlas,activity,agent,region,mode,cut,edges,onSelect,selected}:{atlas:AtlasData;activity?:Activity;agent:number;region:string;mode:string;cut:number;edges:boolean;onSelect:(n:number)=>void;selected:number|null}){
  const {positions,baseColors,center,scale,edgePositions}=useMemo(()=>{
    const box=new THREE.Box3().setFromPoints(atlas.nodes.map(n=>new THREE.Vector3(...n.p)));
    const c=box.getCenter(new THREE.Vector3());const scale=8/box.getSize(new THREE.Vector3()).x;
    const positions=new Float32Array(atlas.nodes.length*3),colors=new Float32Array(atlas.nodes.length*3);
    const color=new THREE.Color();
    atlas.nodes.forEach((n,i)=>{
      positions.set([(n.p[0]-c.x)*scale,-(n.p[1]-c.y)*scale,-(n.p[2]-c.z)*scale],i*3);
      color.set(palette[n.region%palette.length]);colors.set([color.r,color.g,color.b],i*3);
    });
    const edgePositions=new Float32Array(atlas.edges.length*6);
    atlas.edges.forEach(([s,t],i)=>{edgePositions.set(positions.slice(s*3,s*3+3),i*6);edgePositions.set(positions.slice(t*3,t*3+3),i*6+3);});
    return {positions,baseColors:colors,center:c,scale,edgePositions};
  },[atlas]);
  const colors=useMemo(()=>{
    const values=new Float32Array(baseColors);
    const activityMap=new Map(activity?.indices.map((n,i)=>[n,agent===2?Math.abs(activity.a[i]-activity.b[i]):(agent===1?activity.b[i]:activity.a[i])])||[]);
    const neutral=new THREE.Color("#929a9c"),active=new THREE.Color(agent===2?"#df9b58":agent===1?"#d2b185":"#b6d0c1");
    atlas.nodes.forEach((n,i)=>{
      const dim=region!=="all"&&atlas.regions[n.region]!==region;
      let c=mode==="regions"?new THREE.Color().fromArray(baseColors,i*3):neutral.clone();
      if(mode!=="regions"){
        const a=activityMap.get(n.index);
        if(a!==undefined)c.lerp(active,Math.min(1,a/2));
        else c.multiplyScalar(.43);
      }
      if(dim)c.multiplyScalar(.08);
      values.set([c.r,c.g,c.b],i*3);
    });
    return values;
  },[activity,agent,mode,region,baseColors,atlas]);
  const clipPlane=useMemo(()=>new THREE.Plane(new THREE.Vector3(-1,0,0),cut),[cut]);
  const selectedNode=selected===null?undefined:atlas.nodes.find(n=>n.index===selected);
  const selectedPosition=selectedNode?[(selectedNode.p[0]-center.x)*scale,-(selectedNode.p[1]-center.y)*scale,-(selectedNode.p[2]-center.z)*scale] as XYZ:null;
  return <group>
    <points onClick={(e:ThreeEvent<MouseEvent>)=>{e.stopPropagation();if(e.index!==undefined)onSelect(atlas.nodes[e.index].index);}}>
      <bufferGeometry><bufferAttribute attach="attributes-position" args={[positions,3]}/><bufferAttribute attach="attributes-color" args={[colors,3]}/></bufferGeometry>
      <pointsMaterial size={.031} vertexColors sizeAttenuation transparent opacity={.80} depthWrite={false} clippingPlanes={[clipPlane]}/>
    </points>
    {edges&&<lineSegments><bufferGeometry><bufferAttribute attach="attributes-position" args={[edgePositions,3]}/></bufferGeometry><lineBasicMaterial color="#a7b9b4" transparent opacity={.12} depthWrite={false} clippingPlanes={[clipPlane]}/></lineSegments>}
    {selectedPosition&&<group position={selectedPosition}><mesh><sphereGeometry args={[.068,16,12]}/><meshBasicMaterial color="#ecd7ac"/></mesh><Html distanceFactor={12} position={[.15,.2,0]}><div className="brain-tooltip">#{selectedNode!.index}<br/>{selectedNode!.cell_class}</div></Html></group>}
    {cut<4.4&&<mesh position={[cut,0,0]} rotation={[0,Math.PI/2,0]}><planeGeometry args={[6,6]}/><meshBasicMaterial color="#bdc9c1" transparent opacity={.035} side={THREE.DoubleSide} depthWrite={false}/></mesh>}
    <Line points={[[-4.4,-3.2,0],[-2.4,-3.2,0]]} color="#788281" lineWidth={1}/>
    <Html position={[-3.4,-3.5,0]} center style={{pointerEvents:"none"}}><span className="scale-label">{Math.round(2/scale)} μm</span></Html>
  </group>;
}
function BrainCamera({view}:{view:string}){
  const {camera}=useThree();const controls=useRef<any>(null);
  useEffect(()=>{
    camera.position.copy(view==="lateral"?new THREE.Vector3(13,0,0):view==="dorsal"?new THREE.Vector3(0,13,.01):new THREE.Vector3(0,0,13));
    controls.current?.target.set(0,0,0);controls.current?.update();
  },[view,camera]);
  return <OrbitControls ref={controls} enableDamping dampingFactor={.1} minDistance={1.2} maxDistance={24} makeDefault/>;
}
export function BrainScene(props:Parameters<typeof BrainPoints>[0]&{view:string}){
  return <Canvas dpr={[1,2]} camera={{position:[0,0,13],fov:44,near:.01,far:100}} raycaster={{params:{Points:{threshold:.045}}} gl={{antialias:true,localClippingEnabled:true}} onCreated={({gl})=>gl.setClearColor("#181d20")}>
    <BrainPoints {...props}/><BrainCamera view={props.view}/>
  </Canvas>;
}
