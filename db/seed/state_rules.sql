-- PLACEHOLDER RULES. NOT LEGAL ADVICE.
-- Every row ships with legally_reviewed = false. The rules engine treats an
-- unreviewed row as "needs review", so nothing is auto-approved until a lawyer
-- has checked the state's cattle protection, transport and market rules and
-- flipped legally_reviewed to true.
INSERT INTO state_rules (state, species, action, allowed, docs_required, note, legally_reviewed) VALUES
  ('RJ', 'cow',     'sell', true, '["ear_tag"]', 'Pilot placeholder. Check state bovine and transport laws before enabling.', false),
  ('RJ', 'buffalo', 'sell', true, '["ear_tag"]', 'Pilot placeholder.', false),
  ('RJ', 'goat',    'sell', true, '[]',          'Pilot placeholder.', false),
  ('RJ', 'sheep',   'sell', true, '[]',          'Pilot placeholder.', false),
  ('RJ', 'camel',   'sell', true, '[]',          'Pilot placeholder. Camel sale/transport may be specially regulated; verify.', false)
ON CONFLICT (state, species, action) DO NOTHING;
