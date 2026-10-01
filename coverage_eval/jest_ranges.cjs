// Emit source spans of Jest test calls using the TypeScript parser already
// installed by the dashboard. No project source or Jest configuration changes.
const fs = require("fs");
const ts = require(require.resolve("typescript", { paths: [process.cwd()] }));
const filename = process.argv[2];
const source = fs.readFileSync(filename, "utf8");
const kind = filename.endsWith("x") ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
const tree = ts.createSourceFile(filename, source, ts.ScriptTarget.Latest, true, kind);
const ranges = [];
function rootName(expression) {
  while (ts.isPropertyAccessExpression(expression) || ts.isElementAccessExpression(expression)) {
    expression = expression.expression;
  }
  while (ts.isCallExpression(expression)) expression = expression.expression;
  return ts.isIdentifier(expression) ? expression.text : null;
}
function visit(node) {
  if (ts.isCallExpression(node) && ["test", "it", "fit", "xit"].includes(rootName(node.expression))) {
    const start = tree.getLineAndCharacterOfPosition(node.getStart(tree)).line + 1;
    const end = tree.getLineAndCharacterOfPosition(node.getEnd() - 1).line + 1;
    ranges.push({ start, end });
  }
  ts.forEachChild(node, visit);
}
visit(tree);
process.stdout.write(JSON.stringify(ranges));
