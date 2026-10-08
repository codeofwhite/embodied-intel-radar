import { index, integer, sqliteTable, text, uniqueIndex } from "drizzle-orm/sqlite-core";

export const radarSnapshots = sqliteTable(
  "radar_snapshots",
  {
    id: integer("id").primaryKey({ autoIncrement: true }),
    generatedAt: text("generated_at").notNull(),
    receivedAt: text("received_at").notNull(),
    jobsJson: text("jobs_json").notNull(),
    eventsJson: text("events_json").notNull(),
    socialJson: text("social_json").notNull(),
    quotesJson: text("quotes_json").notNull(),
    refreshJson: text("refresh_json").notNull(),
  },
  (table) => [index("idx_radar_snapshots_generated_at").on(table.generatedAt)],
);

export const refreshRequests = sqliteTable(
  "refresh_requests",
  {
    id: text("id").primaryKey(),
    status: text("status").notNull(),
    requestedAt: text("requested_at").notNull(),
    claimedAt: text("claimed_at"),
    finishedAt: text("finished_at"),
    message: text("message"),
  },
  (table) => [index("idx_refresh_requests_status_requested").on(table.status, table.requestedAt)],
);

export const socialSignals = sqliteTable(
  "social_signals",
  {
    id: text("id").primaryKey(),
    platform: text("platform").notNull(),
    url: text("url").notNull(),
    title: text("title").notNull(),
    note: text("note").notNull().default(""),
    signalType: text("signal_type").notNull(),
    company: text("company").notNull().default(""),
    role: text("role").notNull().default(""),
    tagsJson: text("tags_json").notNull().default("[]"),
    publishedAt: text("published_at"),
    createdAt: text("created_at").notNull(),
  },
  (table) => [
    uniqueIndex("uq_social_signals_url").on(table.url),
    index("idx_social_signals_created_at").on(table.createdAt),
  ],
);
