CREATE TABLE `radar_snapshots` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`generated_at` text NOT NULL,
	`received_at` text NOT NULL,
	`jobs_json` text NOT NULL,
	`events_json` text NOT NULL,
	`social_json` text NOT NULL,
	`quotes_json` text NOT NULL,
	`refresh_json` text NOT NULL
);
--> statement-breakpoint
CREATE INDEX `idx_radar_snapshots_generated_at` ON `radar_snapshots` (`generated_at`);--> statement-breakpoint
CREATE TABLE `refresh_requests` (
	`id` text PRIMARY KEY NOT NULL,
	`status` text NOT NULL,
	`requested_at` text NOT NULL,
	`claimed_at` text,
	`finished_at` text,
	`message` text
);
--> statement-breakpoint
CREATE INDEX `idx_refresh_requests_status_requested` ON `refresh_requests` (`status`,`requested_at`);