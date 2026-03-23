-- Drop existing tables (order matters due to FK)
DROP TABLE IF EXISTS device_tokens;
DROP TABLE IF EXISTS notification_logs;
DROP TABLE IF EXISTS dose_logs;
DROP TABLE IF EXISTS schedules;
DROP TABLE IF EXISTS medications;
DROP TABLE IF EXISTS users;

-- users (synced with auth.users)
CREATE TABLE users (
                       id           UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
                       email        TEXT UNIQUE,
                       name         TEXT NOT NULL DEFAULT '',
                       timezone     TEXT NOT NULL DEFAULT 'Asia/Seoul',
                       language     TEXT NOT NULL DEFAULT 'ko',
                       provider     TEXT NOT NULL DEFAULT 'email',
                       created_at   TIMESTAMPTZ DEFAULT now(),
                       deleted_at   TIMESTAMPTZ
);

-- medications
CREATE TABLE medications (
                             id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                             user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                             name         TEXT NOT NULL,
                             dosage       TEXT,
                             color_tag    TEXT DEFAULT '#1D9E75',
                             memo         TEXT,
                             is_active    BOOLEAN DEFAULT true,
                             created_at   TIMESTAMPTZ DEFAULT now(),
                             deleted_at   TIMESTAMPTZ
);
CREATE INDEX idx_medications_user ON medications(user_id)
    WHERE deleted_at IS NULL;

-- schedules
CREATE TABLE schedules (
                           id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                           medication_id  UUID NOT NULL REFERENCES medications(id) ON DELETE CASCADE,
                           scheduled_time TIME NOT NULL,
                           cycle_type     TEXT NOT NULL,
                           cycle_value    JSONB,
                           is_active      BOOLEAN DEFAULT true
);
CREATE INDEX idx_schedules_medication ON schedules(medication_id);

-- dose_logs
CREATE TABLE dose_logs (
                           id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                           schedule_id  UUID NOT NULL REFERENCES schedules(id),
                           user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                           log_date     DATE NOT NULL,
                           status       TEXT NOT NULL DEFAULT 'pending',
                           taken_at     TIMESTAMPTZ,
                           created_at   TIMESTAMPTZ DEFAULT now(),
                           UNIQUE (schedule_id, log_date)
);
CREATE INDEX idx_dose_logs_user_date ON dose_logs(user_id, log_date DESC);
CREATE INDEX idx_dose_logs_schedule  ON dose_logs(schedule_id);

-- notification_logs
CREATE TABLE notification_logs (
                                   id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                                   schedule_id  UUID NOT NULL REFERENCES schedules(id),
                                   user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                                   sent_at      TIMESTAMPTZ DEFAULT now(),
                                   status       TEXT NOT NULL,
                                   snooze_count INT DEFAULT 0
);
CREATE INDEX idx_notif_logs_user ON notification_logs(user_id, sent_at DESC);

-- device_tokens
CREATE TABLE device_tokens (
                               id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                               user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                               token        TEXT NOT NULL UNIQUE,
                               platform     TEXT NOT NULL,
                               updated_at   TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_device_tokens_user ON device_tokens(user_id);