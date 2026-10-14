const fs=require("fs"),glob=require("glob"),{parse}=require("graphql");
const files=glob.sync("src/**/*.ts").filter(f=>!/generated|test/.test(f));
const out=[];
for(const f of files){const s=fs.readFileSync(f,"utf8");const re=/gql`([\s\S]*?)`/g;let m;
while((m=re.exec(s))){let d;try{d=parse(m[1].replace(/\$\{[^}]*\}/g,""))}catch(e){continue}
for(const def of d.definitions) if(def.kind==="OperationDefinition"&&def.operation==="mutation"){const n=def.selectionSet.selections.length; if(n>1) out.push([n,def.name&&def.name.value,f]);}}}
out.sort((a,b)=>b[0]-a[0]);for(const o of out)console.log(o.join(" "));
