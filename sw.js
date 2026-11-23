/* 오프라인용: 페이지·사진(암호화된 그대로)·글꼴을 기기에 저장 */
const V='ngy-v2';
const CORE=['./','index.html','manifest.webmanifest','photokey.json','icon-192.png','apple-touch-icon.png','nagoya-trip.kml'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(V).then(c=>Promise.all(CORE.map(u=>c.add(u).catch(()=>{})))).then(()=>self.skipWaiting()))});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==V).map(k=>caches.delete(k)))).then(()=>self.clients.claim()))});
async function netFirst(req){const c=await caches.open(V);try{const r=await fetch(req);if(r.ok)c.put(req,r.clone());return r}catch(e){const m=await c.match(req,{ignoreSearch:true});if(m)return m;throw e}}
async function cacheFirst(req){const c=await caches.open(V);const m=await c.match(req);if(m)return m;const r=await fetch(req);if(r.ok)c.put(req,r.clone());return r}
self.addEventListener('fetch',e=>{
  const u=new URL(e.request.url);if(e.request.method!=='GET')return;
  if(u.origin===location.origin){
    if(/\/media\/[0-9a-f]+\.bin$/.test(u.pathname)||/\.(png|kml)$/.test(u.pathname))e.respondWith(cacheFirst(e.request));
    else e.respondWith(netFirst(e.request));
  }else if(/fonts\.(googleapis|gstatic)\.com$/.test(u.hostname))e.respondWith(cacheFirst(e.request));
});
