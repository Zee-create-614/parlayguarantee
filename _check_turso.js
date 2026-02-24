const { createClient } = require('@libsql/client');
const db = createClient({
  url: 'libsql://parlayguarantee-parlayguarantee.aws-us-east-2.turso.io',
  authToken: 'eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NzE3NjQxNzcsImlkIjoiNWZlOTIyMzgtM2RlNC00YzEyLTg1NmMtYWNiNjk0ZjkxNTY2IiwicmlkIjoiZDBhNzE4NzYtNjg5MS00YWE3LThkZGQtZGU0MWM4N2ZjNGZlIn0.tQhQ9DdNqnkIP0rEz0jbOPNhNWTjz4SOcElzp5PGngDPneus0dfp9qvm6GMu7TqMGO8zPH_k_kJFvNP1h3TRBA'
});

async function main() {
  const tables = await db.execute("SELECT name FROM sqlite_master WHERE type='table'");
  console.log('Tables:', JSON.stringify(tables.rows));
  
  try {
    const r = await db.execute("SELECT DISTINCT product, date, count(*) as cnt FROM pick_results GROUP BY product, date ORDER BY date DESC LIMIT 20");
    console.log('Results:', JSON.stringify(r.rows));
  } catch(e) { console.log('No pick_results table:', e.message); }
  
  try {
    const s = await db.execute("SELECT * FROM daily_summaries ORDER BY date DESC LIMIT 20");
    console.log('Summaries:', JSON.stringify(s.rows));
  } catch(e) { console.log('No daily_summaries table:', e.message); }
}
main().catch(console.error);
