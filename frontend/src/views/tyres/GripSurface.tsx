// The grip surface itself: a flat unit grid whose vertex shader lifts each vertex to
// grip = 1 - a*age^b (the served fit, T5), then bends it by the stylised temperature
// factor. The GLSL mirrors src/lib/gripSurface.ts exactly — that twin is what the tests
// pin, since the shader never runs under jsdom. The zone past the fitted support is
// tinted so the cliff and the extrapolation beyond it read at a glance.

import { useEffect, useMemo } from "react";
import { BufferAttribute, BufferGeometry, Color, DoubleSide, ShaderMaterial } from "three";

import type { DegradationCurve } from "../../api/types";
import {
  TYRE_TEMP_AXIS_MAX_C,
  TYRE_TEMP_AXIS_MIN_C,
  TYRE_TEMP_GRIP_PENALTY,
  TYRE_TEMP_REF_C,
} from "../../config/constants";
import { buildGripSurface } from "../../lib/gripSurface";

// stylised — world size of the surface: age runs along X, temperature along Y, grip
// lifts Z (the height). Visual framing only.
const AGE_AXIS_M = 320;
const TEMP_AXIS_M = 320;
const GRIP_HEIGHT_M = 140;

// stylised — grip ramp green (full) to red (worn); the extrapolation past the fitted
// support washes toward amber so a stint stretched past the cliff reads as a warning
const HIGH_GRIP_TINT = "#22c55e";
const LOW_GRIP_TINT = "#dc2626";
const CLIFF_TINT = "#f59e0b";
// stylised — how strongly the extrapolation zone washes amber past the fitted support
const EXTRAPOLATION_WASH = 0.45;

const SURFACE_VERTEX = /* glsl */ `
  uniform float uA;
  uniform float uB;
  uniform float uAgeMax;
  uniform float uTempMin;
  uniform float uTempMax;
  uniform float uTempRef;
  uniform float uTempPenalty;
  uniform float uHeight;
  varying float vGrip;
  varying float vAgeFrac;
  void main() {
    // position.x is the age fraction, position.y the temperature fraction (buildGripSurface)
    float age = position.x * uAgeMax;
    float temp = mix(uTempMin, uTempMax, position.y);
    float fitted = clamp(1.0 - uA * pow(max(age, 0.0), uB), 0.0, 1.0);
    // the stylised temperature factor, exactly 1 at the reference slice
    float span = max(uTempRef - uTempMin, uTempMax - uTempRef);
    float d = abs(temp - uTempRef) / span;
    float grip = clamp(fitted * (1.0 - uTempPenalty * d * d), 0.0, 1.0);
    vGrip = grip;
    vAgeFrac = position.x;
    vec3 lifted = vec3(position.x, position.y, grip * uHeight);
    gl_Position = projectionMatrix * modelViewMatrix * vec4(lifted, 1.0);
  }
`;

const SURFACE_FRAGMENT = /* glsl */ `
  uniform vec3 uHighTint;
  uniform vec3 uLowTint;
  uniform vec3 uCliffTint;
  uniform float uSupportFrac;
  uniform float uExtrapolationWash;
  varying float vGrip;
  varying float vAgeFrac;
  void main() {
    vec3 gripColour = mix(uLowTint, uHighTint, vGrip);
    // step to 1 once age passes the fitted support — everything beyond is extrapolation
    float beyond = step(uSupportFrac, vAgeFrac);
    vec3 colour = mix(gripColour, uCliffTint, beyond * uExtrapolationWash);
    gl_FragColor = vec4(colour, 1.0);
  }
`;

export default function GripSurface({ curve }: { curve: DegradationCurve }) {
  const geometry = useMemo(() => {
    const surface = buildGripSurface(curve);
    const built = new BufferGeometry();
    built.setAttribute("position", new BufferAttribute(surface.positions, 3));
    built.setIndex(new BufferAttribute(surface.indices, 1));
    return built;
  }, [curve]);

  const material = useMemo(() => {
    // a transfer never saw a cliff (max_age_seen null), so its whole surface is
    // extrapolation — supportFrac 0 washes it all amber, matching the low-confidence flag
    const supportFrac =
      curve.max_age_seen !== null ? curve.max_age_seen / curve.cliff_age : 0;
    return new ShaderMaterial({
      vertexShader: SURFACE_VERTEX,
      fragmentShader: SURFACE_FRAGMENT,
      side: DoubleSide,
      uniforms: {
        uA: { value: curve.a },
        uB: { value: curve.b },
        uAgeMax: { value: curve.cliff_age },
        uTempMin: { value: TYRE_TEMP_AXIS_MIN_C },
        uTempMax: { value: TYRE_TEMP_AXIS_MAX_C },
        uTempRef: { value: TYRE_TEMP_REF_C },
        uTempPenalty: { value: TYRE_TEMP_GRIP_PENALTY },
        uHeight: { value: GRIP_HEIGHT_M },
        uSupportFrac: { value: supportFrac },
        uExtrapolationWash: { value: EXTRAPOLATION_WASH },
        uHighTint: { value: new Color(HIGH_GRIP_TINT) },
        uLowTint: { value: new Color(LOW_GRIP_TINT) },
        uCliffTint: { value: new Color(CLIFF_TINT) },
      },
    });
  }, [curve]);

  // geometry and material are built imperatively, outside R3F's auto-dispose — free the
  // GPU buffers when the compound changes or the route unmounts
  useEffect(() => () => {
    geometry.dispose();
    material.dispose();
  }, [geometry, material]);

  return <mesh geometry={geometry} material={material} scale={[AGE_AXIS_M, TEMP_AXIS_M, 1]} />;
}
