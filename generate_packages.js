const fs = require('fs');
const path = require('path');

if (!process.argv.includes('--force')) {
  console.error(
    'Refusing to overwrite generated packages. This scaffold helper is disabled by default.\n' +
      'Run `node generate_packages.js --force` only when you intentionally want to recreate placeholder files.'
  );
  process.exit(1);
}

const packages = ['telegram', 'db', 'atrad'];
const apps = ['ingestor', 'worker'];

const createPkgJson = (name, isApp) => `{
  "name": "${isApp ? '' : '@sentinel/'}${name}",
  "version": "0.1.0",
  ${isApp ? '"private": true,' : '"main": "dist/index.js",\n  "types": "dist/index.d.ts",'}
  "scripts": {
    "build": "tsc",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "@sentinel/core": "workspace:*"
  },
  "devDependencies": {
    "typescript": "^5.4.5"
  }
}`;

const tsconfig = `{
  "extends": "../../tsconfig.json",
  "compilerOptions": {
    "outDir": "dist",
    "rootDir": "src"
  },
  "include": ["src/**/*"],
  "references": [
    { "path": "../core" }
  ]
}`;

for (const pkg of packages) {
  const dir = path.join(__dirname, 'packages', pkg);
  writeFileIfMissing(path.join(dir, 'package.json'), createPkgJson(pkg, false));
  writeFileIfMissing(path.join(dir, 'tsconfig.json'), tsconfig);
  writeFileIfMissing(path.join(dir, 'src', 'index.ts'), '// mock implementation\nexport {};\n');
}

for (const app of apps) {
  const dir = path.join(__dirname, 'apps', app);
  writeFileIfMissing(path.join(dir, 'package.json'), createPkgJson(app, true));
  writeFileIfMissing(path.join(dir, 'tsconfig.json'), tsconfig);
  writeFileIfMissing(path.join(dir, 'src', 'index.ts'), '// mock implementation\nconsole.log("Starting ' + app + '...");\n');
}

function writeFileIfMissing(filePath, contents) {
  if (fs.existsSync(filePath)) {
    console.log(`Skipping existing file: ${path.relative(__dirname, filePath)}`);
    return;
  }

  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, contents);
}
