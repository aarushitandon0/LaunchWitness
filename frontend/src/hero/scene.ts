/**
 * The landing hero: a layered "witness" scene (S10.5b). Six thin, softly folded sheets, one per proof hop (bottom to
 * top: Address, Secure page, Your shop, Order form, Mail server, Your inbox), with the logo resting on top as a glass
 * lens holding a lime check. A soft light carries the test order up the stack; each sheet it passes gets a lime edge;
 * at the top the check lights, holds, and the loop restarts. A small ball circles the stack: the daily check.
 *
 * Loaded with a dynamic import after first paint, from the landing page only. Pauses off-screen and in hidden tabs.
 * Pixel ratio capped at 2. Reduced motion never loads this module (the page shows the still image instead).
 */
import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";

export const HOP_NAMES = ["Address", "Secure page", "Your shop", "Order form", "Mail server", "Your inbox"];

// bottom → top. Warm stone, silver-grey and off-white, with ONE orange and ONE lime sheet (the site's own accents).
const SHEET_COLORS = ["#a79a84", "#b9bcbc", "#e8873c", "#ece6da", "#cfe64a", "#f7f3ea"];
const LIME = new THREE.Color("#dcf06a");
const SHEET_W = 4.4;
const SHEET_D = 3.3;
const GAP = 0.4;
const LOOP = 9; // seconds: climb, hold at the top, reset
const CLIMB = 0.7; // fraction of the loop spent climbing

export type HeroScene = {
  setSpread: (v: number) => void; // 0..1 from the page scroll: the sheets fan out a little
  dispose: () => void;
  stillDataUrl: () => string; // the fallback image (WebP), rendered from a chosen frame
};

type SheetUniforms = { uTime: { value: number }; uPhase: { value: number }; uEdge: { value: number } };

/** Folds + a ripple moving through the sheet, in the vertex shader (normals from the analytic slope),
 * rounded corners and the lime "proven" edge in the fragment shader. Shared by the colour and shadow materials. */
function patchSheet(material: THREE.Material, u: SheetUniforms, withEdge: boolean) {
  material.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, u);
    shader.vertexShader = shader.vertexShader
      .replace(
        "#include <common>",
        `#include <common>
        uniform float uTime; uniform float uPhase;
        varying vec2 vSheetUv;
        float lwH(vec2 p) {
          float ripple = 0.08 * sin(p.x * 1.1 + uTime * 0.85 + uPhase);        // the ripple travelling through the stack
          float fold = 0.05 * sin(p.y * 1.9 - uTime * 0.55 + uPhase * 1.7);      // a soft cross fold
          float cloth = 0.014 * sin((p.x * 0.8 + p.y) * 4.1 + uTime * 0.4);     // fine cloth
          float curl = 0.06 * smoothstep(0.9, 2.3, p.x) * (1.0 + 0.3 * sin(uTime * 0.7 + uPhase)); // the right edge lifts
          return ripple + fold + cloth + curl;
        }`,
      )
      .replace(
        "#include <beginnormal_vertex>",
        `vec2 lwP = position.xy;
        float lwE = 0.01;
        float lwDx = (lwH(lwP + vec2(lwE, 0.0)) - lwH(lwP - vec2(lwE, 0.0))) / (2.0 * lwE);
        float lwDy = (lwH(lwP + vec2(0.0, lwE)) - lwH(lwP - vec2(0.0, lwE))) / (2.0 * lwE);
        vec3 objectNormal = normalize(vec3(-lwDx, -lwDy, 1.0));
        #ifdef USE_TANGENT
          vec3 objectTangent = vec3(1.0, 0.0, 0.0);
        #endif`,
      )
      .replace(
        "#include <begin_vertex>",
        `vec3 transformed = vec3(position.xy, position.z + lwH(position.xy));
        vSheetUv = uv;`,
      );
    shader.fragmentShader = shader.fragmentShader
      .replace(
        "#include <common>",
        `#include <common>
        uniform float uEdge;
        varying vec2 vSheetUv;
        float lwRound(vec2 uv) { // rounded-rectangle distance in sheet units (<0 inside)
          vec2 p = (uv - 0.5) * vec2(${SHEET_W.toFixed(2)}, ${SHEET_D.toFixed(2)});
          vec2 q = abs(p) - vec2(${(SHEET_W / 2 - 0.42).toFixed(3)}, ${(SHEET_D / 2 - 0.42).toFixed(3)});
          return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - 0.42;
        }`,
      )
      .replace(
        "#include <clipping_planes_fragment>",
        `#include <clipping_planes_fragment>
        float lwD = lwRound(vSheetUv);
        if (lwD > 0.0) discard;`,
      );
    if (withEdge) {
      shader.fragmentShader = shader.fragmentShader.replace(
        "#include <emissivemap_fragment>",
        `#include <emissivemap_fragment>
        float lwRim = smoothstep(-0.07, -0.005, lwD);
        totalEmissiveRadiance += vec3(${LIME.r.toFixed(3)}, ${LIME.g.toFixed(3)}, ${LIME.b.toFixed(3)}) * lwRim * uEdge * 1.6;`,
      );
    }
  };
}

/** Fine paper/cloth grain, generated (no image files). */
function grainTexture(): THREE.Texture {
  const c = document.createElement("canvas");
  c.width = c.height = 256;
  const g = c.getContext("2d")!;
  const img = g.createImageData(256, 256);
  for (let i = 0; i < img.data.length; i += 4) {
    const v = 118 + Math.random() * 20;
    img.data[i] = img.data[i + 1] = img.data[i + 2] = v;
    img.data[i + 3] = 255;
  }
  g.putImageData(img, 0, 0);
  const t = new THREE.CanvasTexture(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.repeat.set(3, 3);
  return t;
}

/** A soft round contact shadow under the stack (a radial gradient on a plane). */
function contactShadow(): THREE.Mesh {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const g = c.getContext("2d")!;
  const grad = g.createRadialGradient(64, 64, 4, 64, 64, 64);
  grad.addColorStop(0, "rgba(58,42,22,0.45)");
  grad.addColorStop(0.55, "rgba(58,42,22,0.16)");
  grad.addColorStop(1, "rgba(58,42,22,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, 128, 128);
  const m = new THREE.Mesh(
    new THREE.PlaneGeometry(SHEET_W * 1.7, SHEET_D * 1.7),
    new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(c), transparent: true, depthWrite: false }),
  );
  m.rotation.x = -Math.PI / 2;
  return m;
}

/** The logo as an object: a glass lens (clearcoat + transmission) with a lime check inside and a thin metal rim. */
function lens(): { group: THREE.Group; check: THREE.MeshStandardMaterial } {
  const group = new THREE.Group();
  const R = 0.62;
  const profile: THREE.Vector2[] = [];
  for (let i = 0; i <= 24; i++) {
    const t = i / 24;
    profile.push(new THREE.Vector2(R * Math.sin((t * Math.PI) / 2), 0.2 * Math.cos((t * Math.PI) / 2) + 0.02));
  }
  profile.push(new THREE.Vector2(R, 0));
  const glass = new THREE.Mesh(
    new THREE.LatheGeometry(profile, 64),
    new THREE.MeshPhysicalMaterial({
      color: "#ffffff", metalness: 0, roughness: 0.06, transmission: 1, thickness: 0.35, ior: 1.45,
      clearcoat: 1, clearcoatRoughness: 0.04, attenuationColor: new THREE.Color("#f3f7da"), attenuationDistance: 1.2,
    }),
  );
  glass.castShadow = true;
  group.add(glass);
  const base = new THREE.Mesh(
    new THREE.CylinderGeometry(R, R, 0.05, 64),
    new THREE.MeshStandardMaterial({ color: "#1d1b18", roughness: 0.55 }),
  );
  base.position.y = 0.0;
  base.castShadow = true;
  group.add(base);
  const rim = new THREE.Mesh(
    new THREE.TorusGeometry(R, 0.028, 16, 96),
    new THREE.MeshStandardMaterial({ color: "#d9d6cf", metalness: 1, roughness: 0.22 }),
  );
  rim.rotation.x = Math.PI / 2;
  rim.position.y = 0.025;
  group.add(rim);
  const check = new THREE.MeshStandardMaterial({ color: "#c6db3f", emissive: LIME, emissiveIntensity: 0.15, roughness: 0.35 });
  const path = new THREE.CatmullRomCurve3(
    [new THREE.Vector3(-0.27, 0, -0.04), new THREE.Vector3(-0.17, 0, 0.06), new THREE.Vector3(-0.08, 0, 0.15),
      new THREE.Vector3(0.1, 0, -0.03), new THREE.Vector3(0.3, 0, -0.23)],
    false, "centripetal",
  );
  const tick = new THREE.Mesh(new THREE.TubeGeometry(path, 64, 0.055, 12, false), check);
  tick.position.y = 0.09;
  group.add(tick);
  return { group, check };
}

const smooth = (a: number, b: number, x: number) => {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
};

export function createHeroScene(
  host: HTMLElement,
  labels: HTMLElement[],
  opts: { still?: boolean; visible?: () => { right: number; bottom: number } } = {},
): HeroScene {
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: !!opts.still });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 0.92;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  host.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 0.4;

  const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 100);
  camera.position.set(6.2, 6.6, 8.6);
  camera.lookAt(0, 0.85, 0);

  scene.add(new THREE.HemisphereLight("#fff6e6", "#8f8270", 0.55));
  const sun = new THREE.DirectionalLight("#fff1dc", 2.6);
  sun.position.set(-4, 9, 5);
  sun.castShadow = true;
  sun.shadow.mapSize.set(1024, 1024);
  sun.shadow.camera.left = sun.shadow.camera.bottom = -4.5;
  sun.shadow.camera.right = sun.shadow.camera.top = 4.5;
  sun.shadow.radius = 6;
  sun.shadow.bias = -0.0015;
  scene.add(sun);
  const orderLight = new THREE.PointLight(LIME, 0, 3.2, 1.6); // the test order travelling up
  scene.add(orderLight);

  const stack = new THREE.Group();
  stack.rotation.y = -0.62;
  scene.add(stack);
  const shadow = contactShadow();
  shadow.position.y = -0.02;
  stack.add(shadow);

  const grain = grainTexture();
  const geo = new THREE.PlaneGeometry(SHEET_W, SHEET_D, 96, 72);
  const sheets = SHEET_COLORS.map((color, i) => {
    const u: SheetUniforms = { uTime: { value: 0 }, uPhase: { value: i * 0.75 }, uEdge: { value: 0 } };
    const mat = new THREE.MeshPhysicalMaterial({
      color, roughness: 0.78, metalness: 0, sheen: 0.45, sheenRoughness: 0.6, sheenColor: new THREE.Color("#ffffff"),
      bumpMap: grain, bumpScale: 0.9, side: THREE.DoubleSide, emissive: "#000000",
    });
    patchSheet(mat, u, true);
    const depth = new THREE.MeshDepthMaterial({ depthPacking: THREE.RGBADepthPacking });
    patchSheet(depth, u, false);
    const mesh = new THREE.Mesh(geo, mat);
    mesh.customDepthMaterial = depth;
    mesh.rotation.x = -Math.PI / 2;
    const grow = 1 + (SHEET_COLORS.length - 1 - i) * 0.13; // the bottom sheet is the widest
    mesh.scale.set(grow, grow, 1);
    mesh.position.set((SHEET_COLORS.length - 1 - i) * 0.16, 0.12 + i * GAP, (SHEET_COLORS.length - 1 - i) * 0.1);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    stack.add(mesh);
    return { mesh, u, baseY: mesh.position.y, grow };
  });

  const { group: lensGroup, check } = lens();
  lensGroup.position.y = sheets[sheets.length - 1].baseY + 0.1;
  lensGroup.rotation.y = 0.62 + Math.atan2(6.2, 8.6); // undo the stack's turn, then face the camera
  lensGroup.scale.setScalar(1.15);
  stack.add(lensGroup);

  const ball = new THREE.Mesh(
    new THREE.SphereGeometry(0.17, 32, 24),
    new THREE.MeshPhysicalMaterial({ color: "#d6ec62", roughness: 0.3, clearcoat: 1, clearcoatRoughness: 0.1 }),
  );
  ball.castShadow = true;
  scene.add(ball);

  // ---- sizing, labels ----
  let w = 1;
  let h = 1;
  const resize = () => {
    const r = host.getBoundingClientRect();
    w = Math.max(1, r.width);
    h = Math.max(1, r.height);
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    // keep the stack the same size on screen: narrow boxes move the camera back a little
    const fit = 1.12 * Math.max(1, 1.15 / camera.aspect);
    camera.position.set(6.2 * fit, 6.6 * fit, 8.6 * fit);
    camera.lookAt(0, 0.85, 0);
    camera.updateProjectionMatrix();
  };
  resize();
  const ro = new ResizeObserver(resize);
  ro.observe(host);

  const anchor = new THREE.Vector3();
  const EDGE_POINTS = [-0.9, -0.7, -0.5, -0.3, -0.1].map((f) => new THREE.Vector3(SHEET_W / 2 - 0.12, f * (SHEET_D / 2), 0));
  const placeLabels = () => {
    const v = opts.visible?.(); // once per frame
    sheets.forEach((s, i) => {
      const el = labels[i];
      if (!el) return;
      // the front half of the right edge; the point furthest right on screen, so the label sits just off the sheet
      let bx = -Infinity;
      let by = 0;
      for (const p of EDGE_POINTS) {
        anchor.copy(p).applyMatrix4(s.mesh.matrixWorld).project(camera);
        const x = (anchor.x * 0.5 + 0.5) * w;
        if (x > bx) {
          bx = x;
          by = (-anchor.y * 0.5 + 0.5) * h;
        }
      }
      // keep every label readable inside the card even where its sheet runs past the edge
      if (v) {
        bx = Math.min(bx, v.right - el.offsetWidth - 96); // clear of the card edge and the "Scroll" cue
        by = Math.min(by, v.bottom - 22);
      }
      el.style.transform = `translate3d(${bx.toFixed(1)}px, ${by.toFixed(1)}px, 0)`;
    });
  };

  // ---- the loop ----
  let spread = 0;
  const clock = new THREE.Clock();
  let t = 0;
  const frame = (time: number) => {
    const loop = (time % LOOP) / LOOP;
    const climb = Math.min(1, loop / CLIMB) * (sheets.length - 1); // which hop the order is at (fractional)
    const fade = 1 - smooth(0.9, 0.97, loop);
    stack.position.y = Math.sin(time * 0.55) * 0.06; // the breathing float
    sheets.forEach((s, i) => {
      s.u.uTime.value = time;
      s.mesh.position.y = s.baseY * (1 + spread * 0.45);
      s.u.uEdge.value = smooth(i - 0.35, i + 0.05, climb) * fade;
    });
    lensGroup.position.y = sheets[sheets.length - 1].mesh.position.y + 0.1 + Math.sin(time * 0.9) * 0.015;
    const lit = smooth(CLIMB, CLIMB + 0.04, loop) * fade;
    check.emissiveIntensity = 0.15 + lit * 2.2;
    const y = 0.12 + climb * GAP * (1 + spread * 0.45) + stack.position.y + 0.18;
    orderLight.position.set(0.4, y, 0.6);
    orderLight.intensity = (loop < CLIMB + 0.03 ? 2.4 : 0) * fade;
    const a = time * 0.32; // the daily check, circling the stack
    ball.position.set(Math.cos(a) * 3.1, 1.5 + Math.sin(a * 2) * 0.12 + stack.position.y, Math.sin(a) * 2.4);
    stack.updateMatrixWorld();
    renderer.render(scene, camera);
    placeLabels();
  };

  // ---- run only when visible ----
  let raf = 0;
  let onScreen = true;
  const tick = () => {
    raf = 0;
    t = clock.getElapsedTime();
    frame(t);
    if (onScreen && !document.hidden) raf = requestAnimationFrame(tick);
  };
  const start = () => {
    if (!raf && onScreen && !document.hidden && !opts.still) {
      clock.start();
      clock.elapsedTime = t;
      raf = requestAnimationFrame(tick);
    }
  };
  const stop = () => {
    if (raf) cancelAnimationFrame(raf);
    raf = 0;
    clock.stop();
  };
  const io = new IntersectionObserver((entries) => {
    onScreen = entries.some((e) => e.isIntersecting);
    if (onScreen) start();
    else stop();
  });
  io.observe(host);
  const onVis = () => (document.hidden ? stop() : start());
  document.addEventListener("visibilitychange", onVis);

  if (opts.still) frame(LOOP * (CLIMB + 0.06)); // every sheet proven, the check lit
  else start();

  return {
    setSpread: (v) => {
      spread = Math.min(1, Math.max(0, v));
    },
    stillDataUrl: () => {
      frame(LOOP * (CLIMB + 0.06));
      return renderer.domElement.toDataURL("image/webp", 0.86);
    },
    dispose: () => {
      stop();
      io.disconnect();
      ro.disconnect();
      document.removeEventListener("visibilitychange", onVis);
      scene.traverse((o) => {
        const m = o as THREE.Mesh;
        m.geometry?.dispose();
        const mats = Array.isArray(m.material) ? m.material : m.material ? [m.material] : [];
        mats.forEach((x) => x.dispose());
      });
      grain.dispose();
      pmrem.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    },
  };
}
