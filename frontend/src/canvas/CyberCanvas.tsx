import React, { useEffect, useRef } from "react";
import * as THREE from "three";
import { useAnimation } from "../motion/AnimationContext";
import { AtmosphereNetwork } from "./AtmosphereNetwork";
import { IntelligenceCore } from "./IntelligenceCore";

export function CyberCanvas() {
  const containerRef = useRef<HTMLDivElement>(null);
  const { quality, reducedMotion, mouseRef, sceneParamsRef, pulseTrigger } = useAnimation();

  useEffect(() => {
    const container = containerRef.current;
    if (!container || typeof window === "undefined") return;

    // 1. Scene & Renderer Setup
    const scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x080808, 0.05);

    const camera = new THREE.PerspectiveCamera(
      48,
      window.innerWidth / window.innerHeight,
      0.1,
      60
    );
    camera.position.set(0, 0, 7.5);

    const renderer = new THREE.WebGLRenderer({
      antialias: quality !== "LOW",
      alpha: true,
      powerPreference: "high-performance",
      precision: quality === "LOW" ? "mediump" : "highp",
    });

    // Cap DPR for high performance (max 2 on desktop, 1.2 on mobile)
    const maxDPR = quality === "HIGH" ? Math.min(window.devicePixelRatio, 2) : 1;
    renderer.setPixelRatio(maxDPR);
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setClearColor(0x000000, 0); // Transparent so dark UI styles show through
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.1;

    container.appendChild(renderer.domElement);

    // 2. Lighting
    const ambientLight = new THREE.AmbientLight(0x220505, 1.2);
    scene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight(0xff2222, 1.5);
    dirLight.position.set(4, 6, 5);
    scene.add(dirLight);

    const backLight = new THREE.DirectionalLight(0x440808, 1.0);
    backLight.position.set(-5, -3, -4);
    scene.add(backLight);

    // 3. 3D Elements
    const network = new AtmosphereNetwork(quality);
    scene.add(network.group);

    const core = new IntelligenceCore();
    // Position core slightly to the right where the hero card sits on Overview
    core.group.position.set(1.4, 0.2, 0);
    scene.add(core.group);

    // 4. Smooth Animation Loop
    let animationFrameId: number;
    const clock = new THREE.Clock();
    const currentCamPos = new THREE.Vector3(0, 0, 7.5);
    const currentCamTarget = new THREE.Vector3(0, 0, 0);
    const targetLookAt = new THREE.Vector3(0, 0, 0);

    const renderLoop = () => {
      animationFrameId = requestAnimationFrame(renderLoop);

      const delta = Math.min(clock.getDelta(), 0.1);
      const time = clock.getElapsedTime();

      // Read current scene parameters
      const params = sceneParamsRef.current;

      // Mouse Parallax smooth lerp
      if (!reducedMotion) {
        mouseRef.current.x = THREE.MathUtils.lerp(
          mouseRef.current.x,
          mouseRef.current.targetX,
          0.05
        );
        mouseRef.current.y = THREE.MathUtils.lerp(
          mouseRef.current.y,
          mouseRef.current.targetY,
          0.05
        );
      }

      // Smooth camera interpolation towards route target position
      const parallaxX = reducedMotion ? 0 : mouseRef.current.x * 0.22;
      const parallaxY = reducedMotion ? 0 : mouseRef.current.y * 0.12;

      currentCamPos.x = THREE.MathUtils.lerp(
        currentCamPos.x,
        params.cameraPos[0] + parallaxX,
        0.04
      );
      currentCamPos.y = THREE.MathUtils.lerp(
        currentCamPos.y,
        params.cameraPos[1] + parallaxY,
        0.04
      );
      currentCamPos.z = THREE.MathUtils.lerp(
        currentCamPos.z,
        params.cameraPos[2],
        0.04
      );
      camera.position.copy(currentCamPos);

      // Camera lookAt interpolation
      targetLookAt.set(
        params.cameraTarget[0] + parallaxX * 0.3,
        params.cameraTarget[1] + parallaxY * 0.3,
        params.cameraTarget[2]
      );
      currentCamTarget.lerp(targetLookAt, 0.05);
      camera.lookAt(currentCamTarget);

      // Core visibility & scale transition
      const targetCoreScale = params.coreVisible ? params.coreScale : 0.001;
      core.group.visible = core.group.scale.x > 0.02 || params.coreVisible;
      core.group.scale.lerp(
        new THREE.Vector3(targetCoreScale, targetCoreScale, targetCoreScale),
        0.06
      );

      // Update 3D components if not in reduced motion
      if (!reducedMotion) {
        network.update(
          delta,
          time,
          params.networkActivity,
          params.redLightIntensity,
          pulseTrigger
        );

        if (core.group.visible) {
          core.update(
            delta,
            time,
            1.0,
            params.coreIntensity,
            params.scanSpeed,
            params.redLightIntensity
          );
        }
      }

      renderer.render(scene, camera);
    };

    renderLoop();

    // 5. Resize Handling
    const handleResize = () => {
      if (!container) return;
      camera.aspect = window.innerWidth / window.innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(window.innerWidth, window.innerHeight);
    };

    window.addEventListener("resize", handleResize, { passive: true });

    // 6. Cleanup
    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener("resize", handleResize);

      network.dispose();
      core.dispose();
      renderer.dispose();

      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
    };
  }, [quality, reducedMotion, mouseRef, sceneParamsRef, pulseTrigger]);

  return (
    <div
      ref={containerRef}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 0,
        pointerEvents: "none",
        overflow: "hidden",
      }}
      aria-hidden="true"
    />
  );
}
