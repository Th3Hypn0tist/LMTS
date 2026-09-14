import test from 'node:test';
import assert from 'node:assert/strict';

import {
  channelColor,
  channelFaceColors,
  perFaceColorChannelKeys,
  visitRenderableGroups,
} from '../../lmts/dvs/static/visualizer.js';

const FACE_ORDER = ['z-', 'z+', 'x-', 'x+', 'y-', 'y+'];

function completeFaceChannels() {
  const channels = {};
  for (let faceIndex = 0; faceIndex < FACE_ORDER.length; faceIndex += 1) {
    const face = FACE_ORDER[faceIndex];
    channels[`face.${face}.color.r`] = faceIndex / 10;
    channels[`face.${face}.color.g`] = 0.25;
    channels[`face.${face}.color.b`] = 0.5;
    channels[`face.${face}.color.a`] = face === 'y+' ? 0.5 : 1;
  }
  return channels;
}

test('uniform DVS color supports explicit alpha without per-face semantics', () => {
  assert.deepEqual(
    channelColor({ 'color.r': 0.25, 'color.a': 0.5 }, [0.1, 0.2, 0.3, 1]),
    [0.25, 0.2, 0.3, 0.5],
  );
});

test('per-face DVS colors follow the face order supplied by S3D', () => {
  const channels = completeFaceChannels();
  assert.equal(perFaceColorChannelKeys(channels).length, 24);
  const colors = channelFaceColors(channels, FACE_ORDER);
  assert.equal(colors.length, 6);
  assert.deepEqual(colors[0], [0, 0.25, 0.5, 1]);
  assert.deepEqual(colors[5], [0.5, 0.25, 0.5, 0.5]);
});

test('per-face DVS colors reject partial face sets instead of inventing fallback colors', () => {
  const channels = completeFaceChannels();
  delete channels['face.x+.color.b'];
  assert.throws(
    () => channelFaceColors(channels, FACE_ORDER),
    /require complete 6xRGBA set; missing: face\.x\+\.color\.b/,
  );
});

test('per-face DVS colors reject face ids outside the S3D face order', () => {
  const channels = completeFaceChannels();
  channels['face.front.color.r'] = 1;
  assert.throws(
    () => channelFaceColors(channels, FACE_ORDER),
    /unknown per-face color channel\(s\): face\.front\.color\.r/,
  );
});

test('per-face DVS colors require S3D to provide canonical face order', () => {
  assert.throws(
    () => channelFaceColors(completeFaceChannels(), null),
    /S3D BOX_FACE_ORDER is required/,
  );
});

test('structural group generations recurse without becoming render primitives', () => {
  const generations = [{
    id: 'targets',
    groups: [{
      primitive: 'group',
      visible: true,
      children: [{
        id: 'tests',
        groups: [
          { primitive: 'box', visible: true, channels: { 'position.x': 1 } },
          { primitive: 'box', visible: false, channels: { 'position.x': 2 } },
        ],
      }],
    }],
  }];
  const seen = [];
  visitRenderableGroups(generations, group => seen.push(group.channels['position.x']));
  assert.deepEqual(seen, [1]);
});

test('unknown render primitives fail instead of silently disappearing', () => {
  const generations = [{
    id: 'unknown',
    groups: [{ primitive: 'sphere', visible: true, channels: {} }],
  }];
  assert.throws(
    () => visitRenderableGroups(generations, () => {}),
    /does not support primitive: sphere/,
  );
});
