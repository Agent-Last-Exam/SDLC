const fs = require("fs");
const path = require("path");
const { buildSchema, parse, validate, Kind } = require("graphql");
const glob = require("glob");
const schemaPath = process.argv[2];
const schema = buildSchema(fs.readFileSync(schemaPath, "utf8"));
const files = glob.sync("src/**/{queries,mutations,subscriptions}.ts").concat(glob.sync("src/**/fragments/*.ts")).concat(glob.sync("src/searches/*.ts"));
const defs = [];
for (const f of files) {
  const src = fs.readFileSync(f, "utf8");
  const re = /gql`([\s\S]*?)`/g; let m;
  while ((m = re.exec(src))) {
    const body = m[1].replace(/\$\{[^}]*\}/g, "");
    try { defs.push(...parse(body).definitions.map(d => ({d, f}))); } catch (e) { console.log("PARSE", f, e.message); }
  }
}
const doc = { kind: Kind.DOCUMENT, definitions: defs.map(x => x.d) };
const errs = validate(schema, doc).filter(e => !/Unknown fragment|Fragment .* is never used|There can be only one/.test(e.message));
const seen = new Set();
for (const e of errs) { if (!seen.has(e.message)) { seen.add(e.message); console.log(e.message); } }
console.log("total", errs.length, "defs", defs.length);
