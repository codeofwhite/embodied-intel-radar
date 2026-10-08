declare namespace Cloudflare {
  interface Env {
    DB?: D1Database;
    BUCKET?: R2Bucket;
    RADAR_INGEST_SECRET?: string;
  }
}
