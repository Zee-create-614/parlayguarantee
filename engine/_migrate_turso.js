import { createClient } from '@libsql/client';

const turso = createClient({
  url: 'libsql://parlayguarantee-parlayguarantee.aws-us-east-2.turso.io',
  authToken: 'eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NzE3NjQxNzcsImlkIjoiNWZlOTIyMzgtM2RlNC00YzEyLTg1NmMtYWNiNjk0ZjkxNTY2IiwicmlkIjoiZDBhNzE4NzYtNjg5MS00YWE3LThkZGQtZGU0MWM4N2ZjNGZlIn0.tQhQ9DdNqnkIP0rEz0jbOPNhNWTjz4SOcElzp5PGngDPneus0dfp9qvm6GMu7TqMGO8zPH_k_kJFvNP1h3TRBA',
});

async function main() {
  // Add missing columns to pick_results
  const prMissing = ['created_at TEXT', 'spread REAL', 'spread_pick TEXT', 'spread_correct INTEGER', 'pick_label TEXT', 'upset_score REAL', 'value_score REAL', 'sport TEXT', 'bet_type TEXT', 'ou_pick TEXT', 'total_line REAL', 'total_actual REAL', 'ou_correct INTEGER'];
  for (const col of prMissing) {
    try {
      await turso.execute(`ALTER TABLE pick_results ADD COLUMN ${col}`);
      console.log(`Added pick_results.${col.split(' ')[0]}`);
    } catch (e) { /* already exists */ }
  }

  // Add missing columns to daily_summaries
  const dsMissing = ['created_at TEXT', 'spread_correct INTEGER', 'spread_total INTEGER', 'spread_accuracy REAL', 'sport TEXT', 'ou_correct INTEGER', 'ou_total INTEGER', 'ou_accuracy REAL'];
  for (const col of dsMissing) {
    try {
      await turso.execute(`ALTER TABLE daily_summaries ADD COLUMN ${col}`);
      console.log(`Added daily_summaries.${col.split(' ')[0]}`);
    } catch (e) { /* already exists */ }
  }

  // Clear and re-push
  await turso.execute('DELETE FROM pick_results');
  await turso.execute('DELETE FROM daily_summaries');
  console.log('Cleared tables, ready for re-push');
}

main().catch(console.error);
