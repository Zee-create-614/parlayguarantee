// Setup script for Turso database
// Run this manually to create the database and get connection details

const crypto = require('crypto');

console.log(`
TURSO DATABASE SETUP INSTRUCTIONS:

1. Go to turso.tech and sign up for free
2. Create a database named 'parlayguarantee'
3. Get your database URL (looks like: libsql://database-name-org.turso.io)
4. Get your auth token from the dashboard
5. Add these to your .env.local file:

TURSO_DATABASE_URL=your-database-url-here
TURSO_AUTH_TOKEN=your-auth-token-here

Example:
TURSO_DATABASE_URL=libsql://parlayguarantee-mybotzee-6360.turso.io
TURSO_AUTH_TOKEN=eyJhbGciOiJFZERTQS...

Alternatively, use the Turso CLI:
1. Install: npm install -g turso
2. Signup: turso auth signup
3. Create DB: turso db create parlayguarantee
4. Get URL: turso db show parlayguarantee --url
5. Get token: turso db tokens create parlayguarantee

The database schema will be automatically created when the app starts.
`);

// Generate a sample auth token format (not real)
const sampleToken = 'eyJ' + crypto.randomBytes(64).toString('base64') + '...';
console.log('Sample token format:', sampleToken.substring(0, 50) + '...');