// 坐标系转换单元验证：与 index.html 中的实现保持一致
const PI = Math.PI, A = 6378245.0, EE = 0.00669342162296594323;

function outOfChina(lng, lat) {
  return !(lng > 73.66 && lng < 135.05 && lat > 3.86 && lat < 53.55);
}
function tLat(x, y) {
  let r = -100 + 2*x + 3*y + 0.2*y*y + 0.1*x*y + 0.2*Math.sqrt(Math.abs(x));
  r += (20*Math.sin(6*x*PI) + 20*Math.sin(2*x*PI)) * 2/3;
  r += (20*Math.sin(y*PI) + 40*Math.sin(y/3*PI)) * 2/3;
  r += (160*Math.sin(y/12*PI) + 320*Math.sin(y*PI/30)) * 2/3;
  return r;
}
function tLng(x, y) {
  let r = 300 + x + 2*y + 0.1*x*x + 0.1*x*y + 0.1*Math.sqrt(Math.abs(x));
  r += (20*Math.sin(6*x*PI) + 20*Math.sin(2*x*PI)) * 2/3;
  r += (20*Math.sin(x*PI) + 40*Math.sin(x/3*PI)) * 2/3;
  r += (150*Math.sin(x/12*PI) + 300*Math.sin(x/30*PI)) * 2/3;
  return r;
}
function wgs2gcj(lng, lat) {
  if (outOfChina(lng, lat)) return [lng, lat];
  let dLat = tLat(lng - 105, lat - 35), dLng = tLng(lng - 105, lat - 35);
  const rad = lat / 180 * PI;
  let m = Math.sin(rad); m = 1 - EE * m * m;
  const s = Math.sqrt(m);
  dLat = (dLat * 180) / ((A * (1 - EE)) / (m * s) * PI);
  dLng = (dLng * 180) / (A / s * Math.cos(rad) * PI);
  return [lng + dLng, lat + dLat];
}
function gcj2wgs(lng, lat) {
  if (outOfChina(lng, lat)) return [lng, lat];
  let wlng = lng, wlat = lat;
  for (let i = 0; i < 6; i++) {
    const [gl, ga] = wgs2gcj(wlng, wlat);
    wlng += lng - gl; wlat += lat - ga;
  }
  return [wlng, wlat];
}

// 两点间的米级距离（Haversine 简化）
function meters(lng1, lat1, lng2, lat2) {
  const R = 6371000, rad = Math.PI / 180;
  const dLat = (lat2 - lat1) * rad;
  const dLng = (lng2 - lng1) * rad * Math.cos((lat1 + lat2) / 2 * rad);
  return Math.sqrt(dLat * dLat + dLng * dLng) * R;
}

const cases = [
  ['郑州·二七广场', 34.7473, 113.6249],
  ['洛阳·龙门石窟', 34.5557, 112.4698],
  ['北京·天安门',   39.9087, 116.3975],
  ['深圳·市民中心', 22.5455, 114.0546],
  ['乌鲁木齐',      43.8256, 87.6168],
  ['纽约(境外)',    40.6892, -74.0445],
  ['东京(境外)',    35.6586, 139.7454],
];

let fail = 0;
console.log('地点'.padEnd(16) + 'WGS-84 → GCJ-02 偏移'.padEnd(26) + '往返纠偏误差');
console.log('-'.repeat(62));
for (const [name, lat, lng] of cases) {
  const [gl, ga] = wgs2gcj(lng, lat);
  const offset = meters(lng, lat, gl, ga);
  const [rl, ra] = gcj2wgs(gl, ga);
  const roundtrip = meters(lng, lat, rl, ra);

  const domestic = !outOfChina(lng, lat);
  // GCJ-02 偏移量与经纬度相关，境内大致落在 100~800 米区间（新疆偏小、东南沿海偏大）
  let verdict = 'OK';
  if (domestic && (offset < 100 || offset > 800)) verdict = 'FAIL';
  if (!domestic && offset > 0.001) verdict = 'FAIL';
  if (roundtrip > 1) verdict = 'FAIL';
  if (verdict === 'FAIL') fail++;

  console.log(
    name.padEnd(16) +
    (offset.toFixed(1) + ' m').padEnd(26) +
    roundtrip.toFixed(4) + ' m   ' + verdict
  );
}
console.log('-'.repeat(62));
console.log(fail === 0 ? '全部通过：境内偏移量在预期区间，境外零偏移，往返误差 < 1 米'
                       : `${fail} 项未通过`);
