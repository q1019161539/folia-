(()=>{
  if(new URLSearchParams(location.search).get('studioPreview')!=='1'||window.parent===window)return;
  const applyTransform=config=>{
    const root=document.getElementById('root'),value=config?.studioTransform||{};
    if(!root)return;
    const x=Math.max(0,Math.min(100,Number(value.x??50)));
    const y=Math.max(0,Math.min(100,Number(value.y??50)));
    root.style.transform=`translate(${(x-50).toFixed(2)}vw,${(y-50).toFixed(2)}vh)`;
  };
  const token=new URLSearchParams(location.search).get('token')||'';
  const events=new EventSource(`/obs/events?token=${encodeURIComponent(token)}`);
  events.addEventListener('config',event=>{try{applyTransform(JSON.parse(event.data))}catch{}});
  const install=()=>{
    const source=window.parent.document.getElementById('video');
    const root=document.getElementById('root');
    if(!source||!root)return false;
    let mirror=document.getElementById('folia-studio-video');
    if(!mirror){
      mirror=document.createElement('video');
      mirror.id='folia-studio-video';
      mirror.autoplay=true;mirror.muted=true;mirror.playsInline=true;
      mirror.setAttribute('aria-hidden','true');
      Object.assign(mirror.style,{position:'fixed',inset:'0',width:'100%',height:'100%',objectFit:'contain',background:'#000',zIndex:'0',pointerEvents:'none'});
      document.body.prepend(mirror);
      Object.assign(root.style,{position:'relative',zIndex:'1',width:'100vw',height:'100vh'});
    }
    let endedOnce=false,directSyncing=false;
    const useDirectMirror=()=>{
      if(directSyncing)return;
      directSyncing=true;
      try{mirror.pause();mirror.srcObject=null}catch{}
      document.documentElement.dataset.studioVideoBridge='mirror';
      const sync=()=>{
        if(!mirror.isConnected)return;
        const next=source.currentSrc||source.src;
        if(next&&mirror.src!==next)mirror.src=next;
        try{
          if(mirror.readyState>=1&&!mirror.seeking&&Math.abs((mirror.currentTime||0)-(source.currentTime||0))>.08)mirror.currentTime=source.currentTime||0;
          if(source.paused||source.ended)mirror.pause();else mirror.play().catch(()=>{});
        }catch{}
        requestAnimationFrame(sync);
      };
      sync();
    };
    source.addEventListener('ended',()=>{endedOnce=true});
    source.addEventListener('seeking',()=>{if(endedOnce)useDirectMirror()});
    source.addEventListener('play',()=>{if(endedOnce)useDirectMirror();endedOnce=false});
    const capture=source.captureStream||source.mozCaptureStream;
    if(capture){
      try{mirror.srcObject=capture.call(source);mirror.play().catch(()=>{});document.documentElement.dataset.studioVideoBridge='stream';return true}catch{}
    }
    useDirectMirror();return true;
  };
  if(!install())addEventListener('DOMContentLoaded',install,{once:true});
})();
