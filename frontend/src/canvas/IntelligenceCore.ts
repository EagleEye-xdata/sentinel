import * as THREE from "three";

export class IntelligenceCore {
  public group: THREE.Group;

  private coreMesh: THREE.Mesh;
  private coreWireMesh: THREE.Mesh;
  private gyroRing1: THREE.Mesh;
  private gyroRing2: THREE.Mesh;
  private gyroRing3: THREE.Mesh;
  private cageMesh: THREE.Mesh;
  private reticleTicks: THREE.LineSegments;
  private scanRing: THREE.Mesh;
  private gridFloor: THREE.GridHelper;
  private coreLight: THREE.PointLight;

  private orbitParticles: THREE.Points;
  private orbitCount = 48;

  constructor() {
    this.group = new THREE.Group();

    // 1. Central Core (Glowing Icosahedron + Inner Sphere)
    const coreGeo = new THREE.IcosahedronGeometry(0.75, 1);
    const coreMat = new THREE.MeshStandardMaterial({
      color: 0x110303,
      emissive: 0xdc2626,
      emissiveIntensity: 0.85,
      roughness: 0.2,
      metalness: 0.9,
      wireframe: false,
    });
    this.coreMesh = new THREE.Mesh(coreGeo, coreMat);
    this.group.add(this.coreMesh);

    // Inner wireframe lattice for analytical targeting look
    const wireGeo = new THREE.IcosahedronGeometry(0.77, 1);
    const wireMat = new THREE.MeshBasicMaterial({
      color: 0xff4d4d,
      wireframe: true,
      transparent: true,
      opacity: 0.65,
    });
    this.coreWireMesh = new THREE.Mesh(wireGeo, wireMat);
    this.group.add(this.coreWireMesh);

    // 2. Gyroscope Nested Orbital Rings (Iris / Surveillance Architecture)
    const ringMat1 = new THREE.MeshBasicMaterial({
      color: 0xdc2626,
      wireframe: true,
      transparent: true,
      opacity: 0.45,
    });
    const ringMat2 = new THREE.MeshBasicMaterial({
      color: 0x991b1b,
      wireframe: true,
      transparent: true,
      opacity: 0.35,
    });
    const ringMat3 = new THREE.MeshBasicMaterial({
      color: 0xff3b3b,
      wireframe: true,
      transparent: true,
      opacity: 0.25,
    });

    this.gyroRing1 = new THREE.Mesh(new THREE.TorusGeometry(1.25, 0.015, 6, 64), ringMat1);
    this.gyroRing2 = new THREE.Mesh(new THREE.TorusGeometry(1.75, 0.018, 6, 64), ringMat2);
    this.gyroRing3 = new THREE.Mesh(new THREE.TorusGeometry(2.35, 0.012, 6, 64), ringMat3);

    this.gyroRing1.rotation.x = Math.PI / 3;
    this.gyroRing2.rotation.y = Math.PI / 4;
    this.gyroRing3.rotation.z = Math.PI / 6;

    this.group.add(this.gyroRing1);
    this.group.add(this.gyroRing2);
    this.group.add(this.gyroRing3);

    // 3. Angular Geometric Cage (Outer Boundary Defense)
    const cageGeo = new THREE.DodecahedronGeometry(1.9, 0);
    const cageMat = new THREE.MeshBasicMaterial({
      color: 0x661111,
      wireframe: true,
      transparent: true,
      opacity: 0.3,
    });
    this.cageMesh = new THREE.Mesh(cageGeo, cageMat);
    this.group.add(this.cageMesh);

    // 4. Reticle Ticks (Targeting Markers)
    const tickCount = 16;
    const tickPositions = new Float32Array(tickCount * 2 * 3);
    const tickRadius = 2.65;
    for (let i = 0; i < tickCount; i++) {
      const angle = (i / tickCount) * Math.PI * 2;
      const x1 = Math.cos(angle) * tickRadius;
      const y1 = Math.sin(angle) * tickRadius;
      const x2 = Math.cos(angle) * (tickRadius + 0.16);
      const y2 = Math.sin(angle) * (tickRadius + 0.16);

      tickPositions[i * 6 + 0] = x1;
      tickPositions[i * 6 + 1] = y1;
      tickPositions[i * 6 + 2] = 0;

      tickPositions[i * 6 + 3] = x2;
      tickPositions[i * 6 + 4] = y2;
      tickPositions[i * 6 + 5] = 0;
    }
    const tickGeo = new THREE.BufferGeometry();
    tickGeo.setAttribute("position", new THREE.BufferAttribute(tickPositions, 3));
    const tickMat = new THREE.LineBasicMaterial({
      color: 0xdc2626,
      transparent: true,
      opacity: 0.5,
    });
    this.reticleTicks = new THREE.LineSegments(tickGeo, tickMat);
    this.group.add(this.reticleTicks);

    // 5. Scan Sweep Ring
    const scanGeo = new THREE.RingGeometry(0.5, 2.7, 48);
    const scanMat = new THREE.MeshBasicMaterial({
      color: 0xdc2626,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.08,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    this.scanRing = new THREE.Mesh(scanGeo, scanMat);
    this.group.add(this.scanRing);

    // 6. Orbital Particles around Core
    const orbitGeo = new THREE.BufferGeometry();
    const orbitPositions = new Float32Array(this.orbitCount * 3);
    for (let i = 0; i < this.orbitCount; i++) {
      const angle = (i / this.orbitCount) * Math.PI * 2;
      const rad = 1.3 + Math.sin(i * 1.5) * 0.9;
      orbitPositions[i * 3 + 0] = Math.cos(angle) * rad;
      orbitPositions[i * 3 + 1] = (Math.sin(angle * 3) * 0.4);
      orbitPositions[i * 3 + 2] = Math.sin(angle) * rad;
    }
    orbitGeo.setAttribute("position", new THREE.BufferAttribute(orbitPositions, 3));
    const orbitMat = new THREE.PointsMaterial({
      color: 0xff5555,
      size: 0.08,
      transparent: true,
      opacity: 0.7,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    this.orbitParticles = new THREE.Points(orbitGeo, orbitMat);
    this.group.add(this.orbitParticles);

    // 7. Perspective 3D Grid Floor
    this.gridFloor = new THREE.GridHelper(16, 20, 0xdc2626, 0x220505);
    this.gridFloor.position.y = -2.8;
    // Set floor opacity
    if (Array.isArray(this.gridFloor.material)) {
      this.gridFloor.material.forEach((m) => {
        m.transparent = true;
        m.opacity = 0.14;
      });
    } else {
      this.gridFloor.material.transparent = true;
      this.gridFloor.material.opacity = 0.14;
    }
    this.group.add(this.gridFloor);

    // 8. Core Point Light
    this.coreLight = new THREE.PointLight(0xdc2626, 2.2, 8);
    this.group.add(this.coreLight);
  }

  public update(
    delta: number,
    time: number,
    targetScale: number,
    intensity: number,
    scanSpeed: number,
    redIntensity: number
  ) {
    // 1. Organic Core Breathing (Scale & Emissive intensity cycle)
    const breath = 1.0 + Math.sin(time * 1.8) * 0.045;
    const finalScale = targetScale * breath;
    this.coreMesh.scale.set(finalScale, finalScale, finalScale);
    this.coreWireMesh.scale.set(finalScale * 1.02, finalScale * 1.02, finalScale * 1.02);

    const coreMat = this.coreMesh.material as THREE.MeshStandardMaterial;
    coreMat.emissiveIntensity = (0.75 + Math.sin(time * 2.2) * 0.25) * intensity * redIntensity;

    this.coreLight.intensity = (2.0 + Math.sin(time * 2.2) * 0.8) * intensity * redIntensity;

    // 2. Multi-speed Independent Nested Rotations
    // Ring 1 (fastest inner)
    this.gyroRing1.rotation.x += delta * 0.22;
    this.gyroRing1.rotation.y += delta * 0.18;

    // Ring 2 (middle)
    this.gyroRing2.rotation.y -= delta * 0.14;
    this.gyroRing2.rotation.z += delta * 0.12;

    // Ring 3 (outer slowest)
    this.gyroRing3.rotation.x += delta * 0.07;
    this.gyroRing3.rotation.z -= delta * 0.09;

    // Core & Cage
    this.coreMesh.rotation.y += delta * 0.15;
    this.coreWireMesh.rotation.y += delta * 0.15;
    this.coreWireMesh.rotation.x = Math.sin(time * 0.5) * 0.1;

    this.cageMesh.rotation.x += delta * 0.05;
    this.cageMesh.rotation.y += delta * 0.06;

    // Reticle subtle oscillation
    this.reticleTicks.rotation.z = Math.sin(time * 0.3) * 0.15;

    // Orbit particles revolution
    this.orbitParticles.rotation.y += delta * 0.35;
    this.orbitParticles.rotation.x = Math.sin(time * 0.8) * 0.2;

    // 3. Scanning Beam Sweep
    this.scanRing.rotation.z += delta * 0.8 * scanSpeed;
    const scanOpacity = 0.05 + (Math.sin(time * 2.5 * scanSpeed) * 0.5 + 0.5) * 0.08 * redIntensity;
    (this.scanRing.material as THREE.MeshBasicMaterial).opacity = scanOpacity;

    // Grid Floor subtle scroll
    this.gridFloor.position.z = ((time * 0.4) % 1.6) - 0.8;
  }

  public dispose() {
    this.coreMesh.geometry.dispose();
    (this.coreMesh.material as THREE.Material).dispose();

    this.coreWireMesh.geometry.dispose();
    (this.coreWireMesh.material as THREE.Material).dispose();

    this.gyroRing1.geometry.dispose();
    (this.gyroRing1.material as THREE.Material).dispose();

    this.gyroRing2.geometry.dispose();
    (this.gyroRing2.material as THREE.Material).dispose();

    this.gyroRing3.geometry.dispose();
    (this.gyroRing3.material as THREE.Material).dispose();

    this.cageMesh.geometry.dispose();
    (this.cageMesh.material as THREE.Material).dispose();

    this.reticleTicks.geometry.dispose();
    (this.reticleTicks.material as THREE.Material).dispose();

    this.scanRing.geometry.dispose();
    (this.scanRing.material as THREE.Material).dispose();

    this.orbitParticles.geometry.dispose();
    (this.orbitParticles.material as THREE.Material).dispose();

    this.gridFloor.geometry.dispose();
  }
}
