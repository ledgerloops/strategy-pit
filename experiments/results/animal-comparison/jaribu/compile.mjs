import ts from '/workspace/strategy-pit/node_modules/typescript/lib/typescript.js';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
mkdirSync('build/src',{recursive:true});
for (const file of ['BirdsEyeGraph','BirdsEyeWorm']) {
 const source=readFileSync(`src/${file}.ts`,'utf8');
 const out=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}});
 writeFileSync(`build/src/${file}.js`,out.outputText);
}
