import * as THREE from "three";

export class AtmosphereNetwork {
  public group: THREE.Group;
  private nodePoints: THREE.Points;
  private dustPoints: THREE.Points;
  private linesMesh: THREE.LineSegments;
  private packetPoints: THREE.Points;
  private pulseRingMesh: THREE.Mesh;

  private nodeCount = 100;
  private dustCount = 300;
  private packetCount = 16;

  private nodePositions: Float32Array;
  private nodeVelocities: Float32Array;
  private dustPositions: Float32Array;
  private linePositions: Float32Array;

  private packets: Array<{
    startIndex: number;
    endIndex: number;
    progress: number;
    speed: number;
  }> = [];

  private lastPulseTrigger = 0;
  private pulseProgress = 1.0; // 0..1
  private pulseOrigin = new THREE.Vector3(0, 0, 0);

  constructor(quality: "HIGH" | "MEDIUM" | "LOW") {
    this.group = new THREE.Group();

    if (quality === "LOW") {
      this.nodeCount = 45;
      this.dustCount = 120;
      this.packetCount = 8;
    } else if (quality === "MEDIUM") {
      this.nodeCount = 75;
      this.dustCount = 200;
      this.packetCount = 12;
    }

    // 1. Digital Dust (Far Ambient Depth)
    const dustGeo = new THREE.BufferGeometry();
    this.dustPositions = new Float32Array(this.dustCount * 3);
    for (let i = 0; i < this.dustCount; i++) {
      this.dustPositions[i * 3 + 0] = (Math.random() - 0.5) * 32;
      this.dustPositions[i * 3 + 1] = (Math.random() - 0.5) * 22;
      this.dustPositions[i * 3 + 2] = (Math.random() - 0.5) * 18 - 4;
    }
    dustGeo.setAttribute("position", new THREE.BufferAttribute(this.dustPositions, 3));
    const dustMat = new THREE.PointsMaterial({
      color: 0x882222,
      size: 0.05,
      transparent: true,
      opacity: 0.28,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    this.dustPoints = new THREE.Points(dustGeo, dustMat);
    this.group.add(this.dustPoints);

    // 2. Network Nodes
    const nodeGeo = new THREE.BufferGeometry();
    this.nodePositions = new Float32Array(this.nodeCount * 3);
    this.nodeVelocities = new Float32Array(this.nodeCount * 3);
    const nodeColors = new Float32Array(this.nodeCount * 3);

    for (let i = 0; i < this.nodeCount; i++) {
      this.nodePositions[i * 3 + 0] = (Math.random() - 0.5) * 18;
      this.nodePositions[i * 3 + 1] = (Math.random() - 0.5) * 12;
      this.nodePositions[i * 3 + 2] = (Math.random() - 0.5) * 10 - 2;

      this.nodeVelocities[i * 3 + 0] = (Math.random() - 0.5) * 0.08;
      this.nodeVelocities[i * 3 + 1] = (Math.random() - 0.5) * 0.08;
      this.nodeVelocities[i * 3 + 2] = (Math.random() - 0.5) * 0.05;

      // Primary color: soft crimson / cyber red
      nodeColors[i * 3 + 0] = 0.86;
      nodeColors[i * 3 + 1] = 0.15;
      nodeColors[i * 3 + 2] = 0.15;
    }
    nodeGeo.setAttribute("position", new THREE.BufferAttribute(this.nodePositions, 3));
    nodeGeo.setAttribute("color", new THREE.BufferAttribute(nodeColors, 3));

    const nodeMat = new THREE.PointsMaterial({
      size: 0.12,
      vertexColors: true,
      transparent: true,
      opacity: 0.75,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    this.nodePoints = new THREE.Points(nodeGeo, nodeMat);
    this.group.add(this.nodePoints);

    // 3. Connecting Network Lines
    // Allocate buffer for max lines
    const maxLines = this.nodeCount * 4;
    this.linePositions = new Float32Array(maxLines * 2 * 3);
    const lineGeo = new THREE.BufferGeometry();
    lineGeo.setAttribute("position", new THREE.BufferAttribute(this.linePositions, 3));

    const lineMat = new THREE.LineBasicMaterial({
      color: 0xdc2626,
      transparent: true,
      opacity: 0.15,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    this.linesMesh = new THREE.LineSegments(lineGeo, lineMat);
    this.group.add(this.linesMesh);

    // 4. Data Packets traveling along lines
    const packetGeo = new THREE.BufferGeometry();
    const packetPositions = new Float32Array(this.packetCount * 3);
    packetGeo.setAttribute("position", new THREE.BufferAttribute(packetPositions, 3));

    for (let i = 0; i < this.packetCount; i++) {
      this.packets.push({
        startIndex: Math.floor(Math.random() * this.nodeCount),
        endIndex: Math.floor(Math.random() * this.nodeCount),
        progress: Math.random(),
        speed: 0.2 + Math.random() * 0.35,
      });
    }

    const packetMat = new THREE.PointsMaterial({
      color: 0xff4d4d,
      size: 0.18,
      transparent: true,
      opacity: 0.9,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    this.packetPoints = new THREE.Points(packetGeo, packetMat);
    this.group.add(this.packetPoints);

    // 5. Threat Pulse Ring
    const ringGeo = new THREE.RingGeometry(0.1, 0.14, 32);
    const ringMat = new THREE.MeshBasicMaterial({
      color: 0xff2222,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    this.pulseRingMesh = new THREE.Mesh(ringGeo, ringMat);
    this.group.add(this.pulseRingMesh);
  }

  public update(
    delta: number,
    time: number,
    activity: number,
    redIntensity: number,
    pulseTrigger: number
  ) {
    // 1. Slow drift of background dust
    const dustPos = this.dustPoints.geometry.attributes.position as THREE.BufferAttribute;
    const dustArr = dustPos.array as Float32Array;
    for (let i = 0; i < this.dustCount; i++) {
      dustArr[i * 3 + 1] += delta * 0.04;
      if (dustArr[i * 3 + 1] > 11) {
        dustArr[i * 3 + 1] = -11;
      }
    }
    dustPos.needsUpdate = true;

    // 2. Network nodes floating with bounds bounce
    const nodePos = this.nodePoints.geometry.attributes.position as THREE.BufferAttribute;
    const nodeArr = nodePos.array as Float32Array;

    for (let i = 0; i < this.nodeCount; i++) {
      nodeArr[i * 3 + 0] += this.nodeVelocities[i * 3 + 0] * delta * activity;
      nodeArr[i * 3 + 1] += this.nodeVelocities[i * 3 + 1] * delta * activity;
      nodeArr[i * 3 + 2] += this.nodeVelocities[i * 3 + 2] * delta * activity;

      // Soft boundary reflection
      if (Math.abs(nodeArr[i * 3 + 0]) > 9) this.nodeVelocities[i * 3 + 0] *= -1;
      if (Math.abs(nodeArr[i * 3 + 1]) > 6) this.nodeVelocities[i * 3 + 1] *= -1;
      if (Math.abs(nodeArr[i * 3 + 2]) > 5) this.nodeVelocities[i * 3 + 2] *= -1;
    }
    nodePos.needsUpdate = true;

    // 3. Connect close nodes with line segments
    const maxDist = 3.2;
    const linePos = this.linesMesh.geometry.attributes.position as THREE.BufferAttribute;
    const lineArr = linePos.array as Float32Array;
    let lineIdx = 0;
    const maxLineVerts = lineArr.length / 3;

    for (let i = 0; i < this.nodeCount && lineIdx < maxLineVerts - 6; i++) {
      const xi = nodeArr[i * 3 + 0];
      const yi = nodeArr[i * 3 + 1];
      const zi = nodeArr[i * 3 + 2];

      for (let j = i + 1; j < this.nodeCount && lineIdx < maxLineVerts - 6; j++) {
        const dx = xi - nodeArr[j * 3 + 0];
        const dy = yi - nodeArr[j * 3 + 1];
        const dz = zi - nodeArr[j * 3 + 2];
        const distSq = dx * dx + dy * dy + dz * dz;

        if (distSq < maxDist * maxDist) {
          lineArr[lineIdx++] = xi;
          lineArr[lineIdx++] = yi;
          lineArr[lineIdx++] = zi;

          lineArr[lineIdx++] = nodeArr[j * 3 + 0];
          lineArr[lineIdx++] = nodeArr[j * 3 + 1];
          lineArr[lineIdx++] = nodeArr[j * 3 + 2];
        }
      }
    }

    // Zero out remainder
    for (let k = lineIdx; k < maxLineVerts * 3; k++) {
      lineArr[k] = 0;
    }
    this.linesMesh.geometry.setDrawRange(0, lineIdx / 3);
    linePos.needsUpdate = true;

    // Line material dynamic opacity based on activity and red intensity
    const lineMat = this.linesMesh.material as THREE.LineBasicMaterial;
    lineMat.opacity = THREE.MathUtils.lerp(lineMat.opacity, 0.12 * redIntensity, 0.05);

    // 4. Data Packets interpolation
    const packetPosAttr = this.packetPoints.geometry.attributes.position as THREE.BufferAttribute;
    const packetArr = packetPosAttr.array as Float32Array;

    for (let p = 0; p < this.packetCount; p++) {
      const packet = this.packets[p];
      packet.progress += delta * packet.speed * activity;

      if (packet.progress >= 1.0) {
        packet.progress = 0;
        packet.startIndex = packet.endIndex;
        packet.endIndex = Math.floor(Math.random() * this.nodeCount);
      }

      const sx = nodeArr[packet.startIndex * 3 + 0];
      const sy = nodeArr[packet.startIndex * 3 + 1];
      const sz = nodeArr[packet.startIndex * 3 + 2];

      const ex = nodeArr[packet.endIndex * 3 + 0];
      const ey = nodeArr[packet.endIndex * 3 + 1];
      const ez = nodeArr[packet.endIndex * 3 + 2];

      packetArr[p * 3 + 0] = THREE.MathUtils.lerp(sx, ex, packet.progress);
      packetArr[p * 3 + 1] = THREE.MathUtils.lerp(sy, ey, packet.progress);
      packetArr[p * 3 + 2] = THREE.MathUtils.lerp(sz, ez, packet.progress);
    }
    packetPosAttr.needsUpdate = true;

    // 5. Threat Pulse trigger handling
    if (pulseTrigger !== this.lastPulseTrigger) {
      this.lastPulseTrigger = pulseTrigger;
      this.pulseProgress = 0;
      // Pick random node as origin
      const rnd = Math.floor(Math.random() * this.nodeCount);
      this.pulseOrigin.set(
        nodeArr[rnd * 3 + 0],
        nodeArr[rnd * 3 + 1],
        nodeArr[rnd * 3 + 2]
      );
      this.pulseRingMesh.position.copy(this.pulseOrigin);
    }

    if (this.pulseProgress < 1.0) {
      this.pulseProgress += delta * 1.2;
      const scale = 0.2 + this.pulseProgress * 3.5;
      this.pulseRingMesh.scale.set(scale, scale, 1);
      (this.pulseRingMesh.material as THREE.MeshBasicMaterial).opacity = Math.max(
        0,
        (1 - this.pulseProgress) * 0.85
      );
    } else {
      (this.pulseRingMesh.material as THREE.MeshBasicMaterial).opacity = 0;
    }

    // Gentle global rotation of network
    this.group.rotation.y = time * 0.018;
    this.group.rotation.x = Math.sin(time * 0.012) * 0.03;
  }

  public dispose() {
    this.nodePoints.geometry.dispose();
    (this.nodePoints.material as THREE.Material).dispose();

    this.dustPoints.geometry.dispose();
    (this.dustPoints.material as THREE.Material).dispose();

    this.linesMesh.geometry.dispose();
    (this.linesMesh.material as THREE.Material).dispose();

    this.packetPoints.geometry.dispose();
    (this.packetPoints.material as THREE.Material).dispose();

    this.pulseRingMesh.geometry.dispose();
    (this.pulseRingMesh.material as THREE.Material).dispose();
  }
}
