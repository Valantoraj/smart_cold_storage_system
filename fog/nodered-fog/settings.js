module.exports = {
    uiPort: process.env.PORT || 1880,
    mqttReconnectTime: 5000,
    httpAdminRoot: '/admin',
    httpNodeRoot: '/api',
    credentialSecret: 'cold-twin-fog-secret',
    adminAuth: null,
    functionGlobalContext: {
        fogLogic: require('/usr/src/node-red/lib/fog_logic.js'),
        lp:       require('/usr/src/node-red/lib/lineproto.js'),
        rules:    require('/usr/src/node-red/config/rules.json'),
        units:    require('/usr/src/node-red/config/units.json'),
    },
    logging: {
        console: { level: 'info', metrics: false, audit: false }
    },
    editorTheme: {
        projects: { enabled: false }
    }
};
