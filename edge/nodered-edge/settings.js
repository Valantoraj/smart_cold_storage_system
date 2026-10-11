module.exports = {
    uiPort: process.env.PORT || 1880,
    mqttReconnectTime: 5000,
    httpAdminRoot: '/admin',
    httpNodeRoot: '/api',
    credentialSecret: 'cold-twin-edge-secret',
    adminAuth: null,   // no auth in lab
    functionGlobalContext: {
        logic: require('/usr/src/node-red/lib/edge_logic.js'),
        units: require('/usr/src/node-red/config/units.json'),
    },
    logging: {
        console: {
            level: 'info',
            metrics: false,
            audit: false
        }
    },
    editorTheme: {
        projects: { enabled: false }
    }
};
