// T2 (docs/security.md): user and AI text must always render through React's
// escaping. Raw-HTML sinks are forbidden anywhere in the app source.
const files = import.meta.glob(["./**/*.ts", "./**/*.tsx", "!./**/*.test.ts", "!./**/*.test.tsx"], {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

const SINK = /dangerouslySetInnerHTML|\.innerHTML\s*=|\.outerHTML\s*=|insertAdjacentHTML|document\.write\(/;

describe("raw-HTML sinks", () => {
  it("scans the app source", () => {
    expect(Object.keys(files).length).toBeGreaterThan(20);
  });

  it("are not used anywhere in src/", () => {
    const offenders = Object.entries(files)
      .filter(([, text]) => SINK.test(text))
      .map(([path]) => path);
    expect(offenders).toEqual([]);
  });
});
