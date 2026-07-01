-- 0019 — First/last name on profiles.
-- The edit screen lets a household member set voornaam/achternaam separately;
-- display_name stays the single display source everywhere (nav, tiles, subtitle)
-- and is recomposed as "first last" on edit. Backfill existing rows by splitting
-- the current display_name on the first space.
ALTER TABLE users
    ADD COLUMN first_name text,
    ADD COLUMN last_name  text;

UPDATE users
SET first_name = split_part(display_name, ' ', 1),
    last_name  = NULLIF(substr(display_name, strpos(display_name, ' ') + 1), display_name)
WHERE display_name IS NOT NULL AND display_name <> '';
