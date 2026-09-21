import { readFileSync } from "node:fs";

const fixtureDirectory = new URL(
  "../../../docs/contracts/chat-sse/fixtures/",
  import.meta.url,
);

// Fixed contract fixtures only; request data never selects a filesystem path.
export const scenarios = Object.freeze(
  [
    { name: "normal", fixtureFile: "series-1-normal.json" },
    { name: "notice", fixtureFile: "series-2-guard-notice.json" },
  ].map(({ name, fixtureFile }) => {
    const fixture = JSON.parse(
      readFileSync(new URL(fixtureFile, fixtureDirectory), "utf8"),
    );
    return Object.freeze({
      name,
      message: `SLI local validation: ${name}`,
      fixtureFile,
      wireSse: fixture.wire_sse,
      expectedText: fixture.expected_wire_events
        .filter(({ event }) => event === "message" || event === "notice")
        .map(({ data }) => data.text)
        .join(""),
    });
  }),
);
