import { createClient } from '@libsql/client';
import Database from 'better-sqlite3';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const turso = createClient({
  url: 'libsql://parlayguarantee-parlayguarantee.aws-us-east-2.turso.io',
  authToken: 'eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NzE3NjQxNzcsImlkIjoiNWZlOTIyMzgtM2RlNC00YzEyLTg1NmMtYWNiNjk0ZjkxNTY2IiwicmlkIjoiZDBhNzE4NzYtNjg5MS00YWE3LThkZGQtZGU0MWM4N2ZjNGZlIn0.tQhQ9DdNqnkIP0rEz0jbOPNhNWTjz4SOcElzp5PGngDPneus0dfp9qvm6GMu7TqMGO8zPH_k_kJFvNP1h3TRBA',
});

const local = new Database(join(__dirname, 'results.db'), { readonly: true });

async function main() {
  // Check Turso schema
  const prSchema = await turso.execute("PRAGMA table_info(pick_results)");
  console.log('Turso pick_results columns:', prSchema.rows.map(r => r.name));
  const dsSchema = await turso.execute("PRAGMA table_info(daily_summaries)");
  console.log('Turso daily_summaries columns:', dsSchema.rows.map(r => r.name));

  const tursoPrCols = prSchema.rows.map(r => r.name);
  const tursoDsCols = dsSchema.rows.map(r => r.name);

  // Push pick_results
  const picks = local.prepare('SELECT * FROM pick_results').all();
  console.log(`Pushing ${picks.length} pick_results...`);
  for (const pick of picks) {
    const cols = tursoPrCols.filter(c => pick[c] !== undefined);
    const vals = cols.map(c => pick[c] ?? null);
    const placeholders = cols.map(() => '?').join(', ');
    await turso.execute({
      sql: `INSERT OR REPLACE INTO pick_results (${cols.join(', ')}) VALUES (${placeholders})`,
      args: vals,
    });
  }
  console.log('pick_results done');

  // Push daily_summaries
  const summaries = local.prepare('SELECT * FROM daily_summaries').all();
  console.log(`Pushing ${summaries.length} daily_summaries...`);
  for (const s of summaries) {
    const cols = tursoDsCols.filter(c => s[c] !== undefined);
    const vals = cols.map(c => s[c] ?? null);
    const placeholders = cols.map(() => '?').join(', ');
    await turso.execute({
      sql: `INSERT OR REPLACE INTO daily_summaries (${cols.join(', ')}) VALUES (${placeholders})`,
      args: vals,
    });
  }
  console.log('daily_summaries done');

  // Verify
  const prCount = await turso.execute('SELECT COUNT(*) as c FROM pick_results');
  const dsCount = await turso.execute('SELECT COUNT(*) as c FROM daily_summaries');
  console.log(`Turso now has: ${prCount.rows[0].c} pick_results, ${dsCount.rows[0].c} daily_summaries`);
}

main().catch(console.error);
