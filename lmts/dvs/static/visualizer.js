function finite(value, label) {
  const number = Number(value);
  if (!Number.isFinite(number)) throw new Error(`${label} must be finite`);
  return number;
}

function channelVector(channels, prefix, fallback) {
  return fallback.map((value, index) => {
    const key = `${prefix}.${'xyz'[index]}`;
    return Object.hasOwn(channels, key) ? finite(channels[key], key) : value;
  });
}

function colorComponent(channels, key, fallback) {
  const component = Object.hasOwn(channels, key) ? finite(channels[key], key) : fallback;
  if (component < 0 || component > 1) throw new Error(`${key} must be between 0 and 1`);
  return component;
}

function channelColor(channels, fallback) {
  return 'rgba'.split('').map((component, index) => (
    colorComponent(channels, `color.${component}`, fallback[index])
  ));
}

function perFaceColorChannelKeys(channels) {
  return Object.keys(channels).filter(key => /^face\.[^.]+\.color\.[rgba]$/.test(key));
}

function channelFaceColors(channels, faceOrder) {
  const present = perFaceColorChannelKeys(channels);
  if (!present.length) return null;
  if (!Array.isArray(faceOrder) || faceOrder.length !== 6 || faceOrder.some(face => typeof face !== 'string' || !face)) {
    throw new Error('S3D BOX_FACE_ORDER is required for per-face DVS color channels');
  }

  const expected = faceOrder.flatMap(face => 'rgba'.split('').map(component => `face.${face}.color.${component}`));
  const allowed = new Set(expected);
  const unknown = present.filter(key => !allowed.has(key));
  if (unknown.length) throw new Error(`unknown per-face color channel(s): ${unknown.join(', ')}`);
  const missing = expected.filter(key => !Object.hasOwn(channels, key));
  if (missing.length) {
    throw new Error(`per-face color channels require complete ${faceOrder.length}xRGBA set; missing: ${missing.join(', ')}`);
  }

  return faceOrder.map(face => 'rgba'.split('').map(component => {
    const key = `face.${face}.color.${component}`;
    return colorComponent(channels, key, 1);
  }));
}

function visitGroups(generations, visitor) {
  for (const generation of generations ?? []) {
    for (const group of generation.groups ?? []) {
      visitor(group, generation);
      visitGroups(group.children ?? [], visitor);
    }
  }
}

function visitRenderableGroups(generations, visitor) {
  visitGroups(generations, (group, generation) => {
    if (group.visible === false || group.primitive === 'group') return;
    if (group.primitive !== 'box') {
      throw new Error(`S3D visual-plan bridge does not support primitive: ${group.primitive}`);
    }
    visitor(group, generation);
  });
}

class S3DVisualPlanRenderer {
  constructor(canvas, s3d) {
    if (!(canvas instanceof HTMLCanvasElement)) throw new Error('S3D visualizer requires a canvas');
    const gl = canvas.getContext('webgl2', { antialias: true, alpha: false });
    if (!gl) throw new Error('WebGL2 is required by S3D visualizer');
    this.canvas = canvas;
    this.gl = gl;
    this.s3d = s3d;
    this.renderer = new s3d.WebGLBatchRenderer(gl);
    this.camera = new s3d.PerspectiveCamera({ position: [8, 7, 10], target: [0, 1, 0] });
    this.controls = new s3d.OrbitControls(canvas, this.camera);
    this.plan = null;
    this.running = true;
    this.frame = this.frame.bind(this);
    gl.enable(gl.DEPTH_TEST);
    gl.depthFunc(gl.LEQUAL);
    requestAnimationFrame(this.frame);
  }

  destroy() {
    this.running = false;
    this.controls.destroy();
  }

  resize() {
    const ratio = window.devicePixelRatio || 1;
    const width = Math.max(1, Math.round(this.canvas.clientWidth * ratio));
    const height = Math.max(1, Math.round(this.canvas.clientHeight * ratio));
    if (this.canvas.width !== width || this.canvas.height !== height) {
      this.canvas.width = width;
      this.canvas.height = height;
    }
    this.gl.viewport(0, 0, width, height);
    return width / height;
  }

  fitCamera(plan) {
    const points = [];
    visitRenderableGroups(plan.generations, group => {
      const position = channelVector(group.channels ?? {}, 'position', [0, 0, 0]);
      const scale = channelVector(group.channels ?? {}, 'scale', [0.35, 0.35, 0.35]);
      points.push({ position, scale });
    });
    if (!points.length) {
      this.camera.target = [0, 0, 0];
      this.camera.position = [7, 6, 8];
      return;
    }
    const min = [Infinity, Infinity, Infinity];
    const max = [-Infinity, -Infinity, -Infinity];
    for (const { position, scale } of points) {
      for (let axis = 0; axis < 3; axis += 1) {
        min[axis] = Math.min(min[axis], position[axis] - scale[axis]);
        max[axis] = Math.max(max[axis], position[axis] + scale[axis]);
      }
    }
    const target = min.map((value, index) => (value + max[index]) / 2);
    const span = Math.max(2, ...max.map((value, index) => value - min[index]));
    this.camera.target = target;
    this.camera.position = [target[0] + span * 1.15, target[1] + span * 0.9, target[2] + span * 1.35];
  }

  load(plan) {
    if (plan?.format !== 's3d.dvs.visual-plan' || plan?.version !== '1.0') {
      throw new Error('Unsupported DVS visual plan');
    }
    this.plan = plan;
    this.fitCamera(plan);
    this.rebuildPackedStore();
  }

  rebuildPackedStore() {
    const aspect = this.resize();
    const vp = this.camera.viewProjection(aspect);
    this.renderer.begin(vp);
    visitRenderableGroups(this.plan?.generations ?? [], group => {
      const channels = group.channels ?? {};
      const position = channelVector(channels, 'position', [0, 0, 0]);
      const rotation = channelVector(channels, 'rotation', [0, 0, 0]);
      const scale = channelVector(channels, 'scale', [0.35, 0.35, 0.35]);
      if (scale.some(value => value <= 0)) throw new Error('S3D box scale channels must be positive');
      const faceColors = channelFaceColors(channels, this.s3d?.BOX_FACE_ORDER);
      if (faceColors) {
        if (typeof this.renderer.boxFaces !== 'function') {
          throw new Error('loaded S3D renderer does not support per-face box colors');
        }
        this.renderer.boxFaces(position, scale, faceColors, false, { rotation });
      } else {
        const color = channelColor(channels, [0.35, 0.7, 1, 1]);
        this.renderer.box(position, scale, color, false, { rotation });
      }
    });
    this.renderer.commitPersistent();
  }

  frame() {
    if (!this.running) return;
    const aspect = this.resize();
    const gl = this.gl;
    gl.clearColor(0.035, 0.045, 0.06, 1);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    if (this.plan) {
      const vp = this.camera.viewProjection(aspect);
      const basis = this.camera.basis();
      this.renderer.drawPersistent(vp, basis.right, basis.up);
    }
    requestAnimationFrame(this.frame);
  }
}

export {
  S3DVisualPlanRenderer,
  channelColor,
  channelFaceColors,
  channelVector,
  perFaceColorChannelKeys,
  visitGroups,
  visitRenderableGroups,
};
