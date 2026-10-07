#!/usr/bin/env node
'use strict';
const {spawnSync} = require('node:child_process');
const path = require('node:path');
const os = {darwin: 'macos', linux: 'linux'}[process.platform];
const arch = {arm64: 'aarch64', x64: 'x86_64'}[process.arch];
if (!os || !arch) {
  console.error('Unsupported platform. Native Windows is not supported; WSL2 qualification is pending.');
  process.exit(2);
}
try {
  const packagePath = require.resolve(`@mos-eisley/mos-eisley-${os}-${arch}/package.json`);
  const command = path.join(path.dirname(packagePath), 'runtime', 'mos');
  const result = spawnSync(command, process.argv.slice(2), {stdio: 'inherit'});
  if (result.error) throw result.error;
  process.exit(result.status === null ? 2 : result.status);
} catch (error) {
  console.error('Mos Eisley platform package is unavailable. Reinstall with optional dependencies enabled.');
  process.exit(2);
}
