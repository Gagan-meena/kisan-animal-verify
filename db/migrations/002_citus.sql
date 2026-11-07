-- 002_citus.sql : rule 4 - distribute tenant tables by seller_id.
-- Safe to run on plain PostgreSQL: it does nothing when the citus extension is unavailable.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'citus') THEN
    RAISE NOTICE 'citus not available; skipping distribution';
    RETURN;
  END IF;

  CREATE EXTENSION IF NOT EXISTS citus;

  -- sellers is the colocation anchor
  IF NOT EXISTS (SELECT 1 FROM pg_dist_partition WHERE logicalrelid = 'sellers'::regclass) THEN
    PERFORM create_distributed_table('sellers', 'id', shard_count := 32);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_dist_partition WHERE logicalrelid = 'listings'::regclass) THEN
    PERFORM create_distributed_table('listings', 'seller_id', colocate_with := 'sellers');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_dist_partition WHERE logicalrelid = 'animals'::regclass) THEN
    PERFORM create_distributed_table('animals', 'seller_id', colocate_with := 'sellers');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_dist_partition WHERE logicalrelid = 'animal_images'::regclass) THEN
    PERFORM create_distributed_table('animal_images', 'seller_id', colocate_with := 'sellers');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_dist_partition WHERE logicalrelid = 'verifications'::regclass) THEN
    PERFORM create_distributed_table('verifications', 'seller_id', colocate_with := 'sellers');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_dist_partition WHERE logicalrelid = 'reviews'::regclass) THEN
    PERFORM create_distributed_table('reviews', 'seller_id', colocate_with := 'sellers');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_dist_partition WHERE logicalrelid = 'outbox'::regclass) THEN
    PERFORM create_distributed_table('outbox', 'seller_id', colocate_with := 'sellers');
  END IF;
  -- small, read everywhere: replicate to every node
  IF NOT EXISTS (SELECT 1 FROM pg_dist_partition WHERE logicalrelid = 'state_rules'::regclass) THEN
    PERFORM create_reference_table('state_rules');
  END IF;
END $$;
