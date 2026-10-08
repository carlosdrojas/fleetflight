import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { CSS2DObject, CSS2DRenderer } from "three/examples/jsm/renderers/CSS2DRenderer.js";
import { bmsMode, flightProgress, frameAt, hubMode, invMode, invPowerW, type Mode, type NodeId, type Timeline } from "../lib/scene";

// Imperative three.js view: given a Timeline and a time t, draw that instant.
// Nothing here advances the simulation; the React screen owns the clock.

const C = {
  bg: 0x0d1015,
  body: 0x1c2330,
  bodyHi: 0x263042,
  line: 0x2e3746,
  ok: 0x3dbe8b,
  warn: 0xe5a63a,
  fail: 0xff6b57,
  accent: 0x7aa2ff,
  off: 0x4a5464,
  power: 0xffd166,
};

const MODE_COLOR: Record<Mode, number> = { ok: C.ok, warn: C.warn, fail: C.fail, off: C.off, active: C.accent };
const PACKET_COLOR: Record<string, number> = { FAULT: C.warn, ACK: C.ok, CMD: C.accent };

const POS: Record<NodeId | "home", THREE.Vector3> = {
  bms: new THREE.Vector3(-3.4, 0, 1.1),
  hub: new THREE.Vector3(-0.6, 0, -1.9),
  inv: new THREE.Vector3(1.6, 0, 1.1),
  home: new THREE.Vector3(4.6, 0, 1.1),
};
const PORT_Y: Record<NodeId, number> = { bms: 1.75, hub: 0.75, inv: 1.55 };

function label(text: string, cls: string): CSS2DObject {
  const el = document.createElement("div");
  el.className = cls;
  el.textContent = text;
  return new CSS2DObject(el);
}

function std(color: number, emissive = 0x000000, ei = 0): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({ color, emissive, emissiveIntensity: ei, roughness: 0.55, metalness: 0.25 });
}

interface Wire {
  curve: THREE.QuadraticBezierCurve3;
  mat: THREE.MeshStandardMaterial;
}

interface Packet {
  mesh: THREE.Mesh;
  tag: CSS2DObject;
  puff: THREE.Mesh;
}

interface Spark {
  p: THREE.Vector3;
  v: THREE.Vector3;
  life: number;
}

const MAX_SPARKS = 260;

export class SceneView {
  private renderer: THREE.WebGLRenderer;
  private labels: CSS2DRenderer;
  private scene = new THREE.Scene();
  private camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
  private controls: OrbitControls;
  private ro: ResizeObserver;
  private lights: Record<NodeId, THREE.MeshStandardMaterial> = {} as never;
  private bodies: Record<NodeId, THREE.MeshStandardMaterial> = {} as never;
  private stateTags: Record<NodeId, HTMLElement> = {} as never;
  private wires: Record<"bms-hub" | "hub-inv", Wire>;
  private breakMark: THREE.Group;
  private breakTag: CSS2DObject;
  private packets: Packet[] = [];
  private powerDots: THREE.Mesh[] = [];
  private powerCurves: THREE.CatmullRomCurve3[] = [];
  private homeGlow: THREE.MeshStandardMaterial;
  private alarm: THREE.PointLight;
  private hubRing: THREE.Mesh;
  private sparks: Spark[] = [];
  private sparkGeo = new THREE.BufferGeometry();
  private sparkPos = new Float32Array(MAX_SPARKS * 3);
  private sparkCol = new Float32Array(MAX_SPARKS * 3);
  private clock = new THREE.Clock();
  private tl: Timeline | null = null;

  constructor(private host: HTMLElement) {
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setClearColor(C.bg);
    host.appendChild(this.renderer.domElement);
    this.labels = new CSS2DRenderer();
    this.labels.domElement.className = "scene-labels";
    host.appendChild(this.labels.domElement);

    this.controls = new OrbitControls(this.camera, this.labels.domElement);
    this.controls.target.set(0.6, 0.6, -0.2);
    this.controls.enableDamping = true;
    this.controls.minDistance = 6;
    this.controls.maxDistance = 22;
    this.controls.maxPolarAngle = Math.PI * 0.47;
    // Touch screens: a stacked panel that swallows swipes traps the page scroll, so orbiting
    // is a desktop (mouse) feature and swipes scroll the page.
    if (window.matchMedia("(pointer: coarse)").matches) {
      this.controls.enabled = false;
      this.labels.domElement.style.touchAction = "pan-y";
    }

    this.scene.fog = new THREE.Fog(C.bg, 16, 30);
    this.scene.add(new THREE.HemisphereLight(0xbfd2ff, 0x0d1015, 0.9));
    const key = new THREE.DirectionalLight(0xffffff, 1.6);
    key.position.set(4, 9, 6);
    this.scene.add(key);
    this.alarm = new THREE.PointLight(C.fail, 0, 7, 1.6);
    this.alarm.position.copy(POS.inv).add(new THREE.Vector3(0, 2.2, 0.6));
    this.scene.add(this.alarm);

    const floor = new THREE.Mesh(new THREE.CircleGeometry(11, 64), std(0x11161d));
    floor.rotation.x = -Math.PI / 2;
    this.scene.add(floor);
    const grid = new THREE.GridHelper(22, 44, 0x1f2630, 0x171d25);
    grid.position.y = 0.002;
    this.scene.add(grid);

    this.buildBms();
    this.buildHub();
    this.buildInverter();
    this.homeGlow = this.buildHome();
    this.hubRing = this.makeHubRing();

    this.wires = {
      "bms-hub": this.makeWire("bms", "hub"),
      "hub-inv": this.makeWire("hub", "inv"),
    };
    const mid = this.wires["hub-inv"].curve.getPoint(0.5);
    this.breakMark = this.makeBreak(mid);
    this.breakTag = label("LINK DOWN", "scene-tag scene-tag-fail");
    this.breakTag.position.copy(mid).add(new THREE.Vector3(0, 0.55, 0));
    this.scene.add(this.breakTag);

    this.buildPower();
    this.buildSparks();

    this.ro = new ResizeObserver(() => this.resize());
    this.ro.observe(host);
    this.resize();
  }

  setTimeline(tl: Timeline) {
    this.tl = tl;
    for (const p of this.packets) {
      this.scene.remove(p.mesh, p.tag, p.puff);
      p.tag.element.remove();
      for (const m of [p.mesh, p.puff]) {
        m.geometry.dispose();
        (m.material as THREE.Material).dispose();
      }
    }
    this.packets = tl.flights.map((f) => {
      const mesh = new THREE.Mesh(
        new THREE.SphereGeometry(f.kind === "CMD" ? 0.13 : 0.16, 20, 14),
        new THREE.MeshBasicMaterial({ color: f.delayed ? C.warn : PACKET_COLOR[f.kind] ?? C.accent }),
      );
      const tag = label(f.label, `scene-pkt scene-pkt-${f.kind.toLowerCase()}`);
      const puff = new THREE.Mesh(
        new THREE.SphereGeometry(0.12, 16, 12),
        new THREE.MeshBasicMaterial({ color: C.fail, transparent: true, opacity: 0 }),
      );
      mesh.visible = false;
      tag.visible = false;
      puff.visible = false;
      this.scene.add(mesh, tag, puff);
      return { mesh, tag, puff };
    });
  }

  /** Draw time t (ms of simulated time). */
  render(t: number) {
    const dt = Math.min(this.clock.getDelta(), 0.05);
    const wall = this.clock.elapsedTime;
    const tl = this.tl;
    const fr = tl ? frameAt(tl, t) : null;
    if (fr) {
      const violating = fr.violations.length > 0;
      this.setNode("bms", bmsMode(fr.bms), fr.bms.split(" ")[0]);
      const hm = hubMode(fr.hub);
      this.setNode("hub", hm, fr.hub.startsWith("RESTART") ? "RESTARTING" : fr.hub.match(/\b(STOP|DISCHARGE)\b/)?.[1] ?? fr.hub.split(" ")[0]);
      this.hubRing.visible = fr.hub.startsWith("RESTART");
      this.hubRing.rotation.z = wall * 4;
      const im: Mode = violating ? "fail" : invMode(fr.inv);
      this.setNode("inv", im, fr.inv.split(" ")[0] + (invPowerW(fr.inv) ? ` ${invPowerW(fr.inv) / 1000} kW` : ""));

      const down = fr.link.startsWith("DOWN");
      const w = this.wires["hub-inv"];
      w.mat.color.setHex(down ? 0x2a1614 : C.line);
      w.mat.emissive.setHex(down ? C.fail : 0x000000);
      w.mat.emissiveIntensity = down ? 0.25 + 0.15 * Math.sin(wall * 6) : 0;
      this.breakMark.visible = down;
      this.breakTag.visible = down;

      // Power flow battery → inverter → home while the inverter discharges.
      const watts = invPowerW(fr.inv);
      const flowing = watts > 0;
      this.powerDots.forEach((d, i) => {
        d.visible = flowing;
        if (!flowing) return;
        const curve = this.powerCurves[i % this.powerCurves.length];
        const k = (wall * 0.45 + (i / this.powerDots.length) * this.powerCurves.length) % 1;
        d.position.copy(curve.getPoint(k));
        (d.material as THREE.MeshBasicMaterial).color.setHex(violating ? C.fail : C.power);
      });
      this.homeGlow.emissiveIntensity = flowing ? 0.9 : 0.08;
      this.homeGlow.emissive.setHex(violating ? C.fail : C.power);

      // Alarm + sparks at the inverter while an invariant is violated.
      this.alarm.intensity = violating ? 6 + 4 * Math.sin(wall * 14) : 0;
      this.bodies.inv.emissive.setHex(violating ? C.fail : 0x000000);
      this.bodies.inv.emissiveIntensity = violating ? 0.18 + 0.14 * Math.sin(wall * 14) : 0;
      if (violating) this.emitSparks(dt);
    }
    this.updatePackets(t);
    this.updateSparks(dt);
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
    this.labels.render(this.scene, this.camera);
  }

  dispose() {
    this.ro.disconnect();
    this.controls.dispose();
    this.renderer.dispose();
    this.scene.traverse((o) => {
      const m = o as THREE.Mesh;
      m.geometry?.dispose?.();
      const mat = m.material as THREE.Material | THREE.Material[] | undefined;
      if (Array.isArray(mat)) mat.forEach((x) => x.dispose());
      else mat?.dispose?.();
    });
    this.renderer.domElement.remove();
    this.labels.domElement.remove();
  }

  // ---------- building ----------

  private addNodeChrome(id: NodeId, name: string, lightY: number, body: THREE.MeshStandardMaterial) {
    const light = std(C.off, C.off, 1.4);
    const led = new THREE.Mesh(new THREE.SphereGeometry(0.14, 20, 14), light);
    led.position.copy(POS[id]).add(new THREE.Vector3(0, lightY, 0));
    this.scene.add(led);
    this.lights[id] = light;
    this.bodies[id] = body;
    const tag = label(name, "scene-name");
    tag.position.copy(POS[id]).add(new THREE.Vector3(0, lightY + 0.55, 0));
    this.scene.add(tag);
    const st = label("", "scene-state");
    st.position.copy(POS[id]).add(new THREE.Vector3(0, -0.05, 1.05));
    this.scene.add(st);
    this.stateTags[id] = st.element;
  }

  private buildBms() {
    const g = new THREE.Group();
    const body = std(C.body);
    const box = new THREE.Mesh(new THREE.BoxGeometry(1.5, 1.6, 1.1), body);
    box.position.y = 0.8;
    g.add(box);
    // Cell stack on the front face.
    for (let i = 0; i < 4; i++) {
      const cell = new THREE.Mesh(new THREE.BoxGeometry(0.28, 1.15, 0.06), std(C.bodyHi));
      cell.position.set(-0.51 + i * 0.34, 0.8, 0.57);
      g.add(cell);
    }
    g.position.copy(POS.bms);
    this.scene.add(g);
    this.addNodeChrome("bms", "BMS", 1.85, body);
  }

  private buildHub() {
    const g = new THREE.Group();
    const body = std(C.body);
    const box = new THREE.Mesh(new THREE.BoxGeometry(1.2, 0.55, 0.9), body);
    box.position.y = 0.28;
    g.add(box);
    const mast = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.7), std(C.line));
    mast.position.set(0.4, 0.9, -0.2);
    g.add(mast);
    g.position.copy(POS.hub);
    this.scene.add(g);
    this.addNodeChrome("hub", "Hub", 0.75, body);
  }

  private buildInverter() {
    const g = new THREE.Group();
    const body = std(C.body);
    const box = new THREE.Mesh(new THREE.BoxGeometry(1.1, 1.4, 0.75), body);
    box.position.y = 0.7;
    g.add(box);
    for (let i = 0; i < 6; i++) {
      const fin = new THREE.Mesh(new THREE.BoxGeometry(0.05, 1.05, 0.22), std(C.bodyHi));
      fin.position.set(-0.4 + i * 0.16, 0.7, -0.45);
      g.add(fin);
    }
    g.position.copy(POS.inv);
    this.scene.add(g);
    this.addNodeChrome("inv", "Inverter", 1.65, body);
  }

  private buildHome(): THREE.MeshStandardMaterial {
    const g = new THREE.Group();
    const walls = new THREE.Mesh(new THREE.BoxGeometry(1.2, 0.85, 1.0), std(0x161c25));
    walls.position.y = 0.43;
    g.add(walls);
    const roof = new THREE.Mesh(new THREE.ConeGeometry(0.95, 0.6, 4), std(0x1c2330));
    roof.position.y = 1.15;
    roof.rotation.y = Math.PI / 4;
    g.add(roof);
    const glow = std(0x2a2416, C.power, 0.1);
    const win = new THREE.Mesh(new THREE.PlaneGeometry(0.34, 0.3), glow);
    win.position.set(0, 0.48, 0.505);
    g.add(win);
    g.position.copy(POS.home);
    this.scene.add(g);
    const tag = label("Home load", "scene-name scene-name-dim");
    tag.position.copy(POS.home).add(new THREE.Vector3(0, 1.75, 0));
    this.scene.add(tag);
    return glow;
  }

  private makeHubRing(): THREE.Mesh {
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(0.85, 0.04, 8, 48, Math.PI * 1.4),
      new THREE.MeshBasicMaterial({ color: C.warn }),
    );
    ring.position.copy(POS.hub).add(new THREE.Vector3(0, 0.05, 0));
    ring.rotation.x = -Math.PI / 2;
    ring.visible = false;
    this.scene.add(ring);
    return ring;
  }

  private port(id: NodeId) {
    return POS[id].clone().add(new THREE.Vector3(0, PORT_Y[id], 0));
  }

  private makeWire(a: NodeId, b: NodeId): Wire {
    const p0 = this.port(a);
    const p2 = this.port(b);
    const p1 = p0.clone().lerp(p2, 0.5).add(new THREE.Vector3(0, 1.0, 0));
    const curve = new THREE.QuadraticBezierCurve3(p0, p1, p2);
    const mat = std(C.line);
    this.scene.add(new THREE.Mesh(new THREE.TubeGeometry(curve, 48, 0.035, 8), mat));
    return { curve, mat };
  }

  private makeBreak(at: THREE.Vector3): THREE.Group {
    const g = new THREE.Group();
    const m = new THREE.MeshBasicMaterial({ color: C.fail });
    for (const r of [Math.PI / 4, -Math.PI / 4]) {
      const bar = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.07, 0.07), m);
      bar.rotation.z = r;
      g.add(bar);
    }
    g.position.copy(at);
    g.visible = false;
    this.scene.add(g);
    return g;
  }

  private buildPower() {
    const y = 0.06;
    const a = POS.bms.clone().add(new THREE.Vector3(0.75, y, 0));
    const b = POS.inv.clone().add(new THREE.Vector3(-0.55, y, 0));
    const c = POS.inv.clone().add(new THREE.Vector3(0.55, y, 0));
    const d = POS.home.clone().add(new THREE.Vector3(-0.6, y, 0));
    this.powerCurves = [new THREE.CatmullRomCurve3([a, b]), new THREE.CatmullRomCurve3([c, d])];
    for (const curve of this.powerCurves) {
      this.scene.add(new THREE.Mesh(new THREE.TubeGeometry(curve, 8, 0.07, 8), std(0x232a35)));
    }
    for (let i = 0; i < 14; i++) {
      const dot = new THREE.Mesh(new THREE.SphereGeometry(0.075, 10, 8), new THREE.MeshBasicMaterial({ color: C.power }));
      dot.visible = false;
      this.powerDots.push(dot);
      this.scene.add(dot);
    }
  }

  private buildSparks() {
    this.sparkGeo.setAttribute("position", new THREE.BufferAttribute(this.sparkPos, 3));
    this.sparkGeo.setAttribute("color", new THREE.BufferAttribute(this.sparkCol, 3));
    this.sparkGeo.setDrawRange(0, 0);
    const mat = new THREE.PointsMaterial({ size: 0.14, vertexColors: true, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false });
    this.scene.add(new THREE.Points(this.sparkGeo, mat));
  }

  // ---------- per frame ----------

  private setNode(id: NodeId, mode: Mode, text: string) {
    const col = MODE_COLOR[mode];
    this.lights[id].color.setHex(col);
    this.lights[id].emissive.setHex(col);
    const el = this.stateTags[id];
    if (el.textContent !== text) el.textContent = text;
    const cls = `scene-state scene-state-${mode}`;
    if (el.className !== cls) el.className = cls;
  }

  private updatePackets(t: number) {
    const tl = this.tl;
    if (!tl) return;
    tl.flights.forEach((f, i) => {
      const pk = this.packets[i];
      if (!pk) return;
      const curve = f.from === "hub" || f.to === "hub" ? this.wires[f.from === "inv" || f.to === "inv" ? "hub-inv" : "bms-hub"].curve : null;
      if (!curve) return;
      const prog = flightProgress(f, t);
      const forward = (f.from === "bms" && f.to === "hub") || (f.from === "hub" && f.to === "inv");
      // A dropped message leaves a short red puff where the wire is broken.
      const puffing = f.fate === "lost" && t > f.t1 && t < f.t1 + 70;
      pk.puff.visible = puffing;
      if (puffing) {
        const k = (t - f.t1) / 70;
        pk.puff.position.copy(curve.getPoint(0.5));
        pk.puff.scale.setScalar(1 + k * 3);
        (pk.puff.material as THREE.MeshBasicMaterial).opacity = 0.7 * (1 - k);
      }
      if (prog === null) {
        pk.mesh.visible = false;
        pk.tag.visible = false;
        return;
      }
      const pos = curve.getPoint(forward ? prog : 1 - prog);
      pk.mesh.position.copy(pos);
      pk.tag.position.copy(pos).add(new THREE.Vector3(0, 0.32, 0));
      pk.mesh.visible = true;
      pk.tag.visible = true;
    });
  }

  private emitSparks(dt: number) {
    const n = Math.min(MAX_SPARKS - this.sparks.length, Math.ceil(dt * 260));
    const origin = POS.inv.clone().add(new THREE.Vector3(0, 1.45, 0.2));
    for (let i = 0; i < n; i++) {
      const a = Math.random() * Math.PI * 2;
      const s = 1.2 + Math.random() * 2.2;
      this.sparks.push({
        p: origin.clone().add(new THREE.Vector3((Math.random() - 0.5) * 0.8, Math.random() * 0.2, (Math.random() - 0.5) * 0.5)),
        v: new THREE.Vector3(Math.cos(a) * s * 0.6, 2 + Math.random() * 2.5, Math.sin(a) * s * 0.6),
        life: 0.5 + Math.random() * 0.6,
      });
    }
  }

  private updateSparks(dt: number) {
    const g = -9.8;
    this.sparks = this.sparks.filter((s) => (s.life -= dt) > 0 && s.p.y > 0);
    this.sparks.forEach((s, i) => {
      s.v.y += g * dt;
      s.p.addScaledVector(s.v, dt);
      this.sparkPos.set([s.p.x, s.p.y, s.p.z], i * 3);
      const k = Math.min(1, s.life * 1.6);
      this.sparkCol.set([1, 0.55 + 0.4 * k, 0.2 * k], i * 3);
    });
    this.sparkGeo.setDrawRange(0, this.sparks.length);
    (this.sparkGeo.attributes.position as THREE.BufferAttribute).needsUpdate = true;
    (this.sparkGeo.attributes.color as THREE.BufferAttribute).needsUpdate = true;
  }

  private resize() {
    const w = this.host.clientWidth || 1;
    const h = this.host.clientHeight || 1;
    this.renderer.setSize(w, h);
    this.labels.setSize(w, h);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.fitCamera();
  }

  /** Back the camera off until the whole bench (BMS … home) fits the panel's width. */
  private fitCamera() {
    const halfWidth = 5.6;
    const vfov = THREE.MathUtils.degToRad(this.camera.fov);
    const hfov = 2 * Math.atan(Math.tan(vfov / 2) * this.camera.aspect);
    const dist = Math.max(10, (halfWidth / Math.tan(hfov / 2)) * 1.05);
    const dir = new THREE.Vector3(0, 0.62, 0.78).normalize();
    this.camera.position.copy(this.controls.target).addScaledVector(dir, dist);
    this.controls.maxDistance = Math.max(22, dist * 1.4);
    this.controls.update();
  }
}
