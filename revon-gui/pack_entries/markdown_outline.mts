import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

type Heading = { line: number; level: number; title: string; anchor: string };
const { default: Slugger } = await import(pathToFileURL(process.argv[2]).href);
const slugger = new Slugger();
const { text }: { text: string } = JSON.parse(readFileSync(0, "utf8"));
const headings: Heading[] = [];
let fence = "";
for (const [index, line] of text.split(/\r?\n/).entries()) {
  const marker = /^ {0,3}(`{3,}|~{3,})(.*)$/.exec(line);
  if (fence) {
    if (marker && marker[1][0] === fence[0] && marker[1].length >= fence.length && !marker[2].trim()) fence = "";
    continue;
  }
  if (marker) {
    fence = marker[1];
    continue;
  }
  const match = /^ {0,3}(#{1,6})(?:[ \t]+(.*)|$)/.exec(line);
  if (match) {
    const title = (match[2] ?? "").replace(/(?:^|[ \t]+)#+[ \t]*$/, "").trim();
    headings.push({ line: index + 1, level: match[1].length, title, anchor: slugger.slug(title) });
    if (headings.length === 256) break;
  }
}
process.stdout.write(JSON.stringify({ headings }));
