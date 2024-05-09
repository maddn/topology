import * as esbuild from 'esbuild';

await esbuild.build({
  entryPoints: [ 'telnet-proxy.mjs' ],
  outdir: '../../webui',
  platform: 'node',
  bundle: true,
  minify: true
});
