// Generic, reusable database on an existing PostgreSQL flexible server.
// The server is referenced by name and must already exist in this resource group.

param serverName string
param name string
param charset string = 'UTF8'
param collation string = 'en_US.utf8'

resource server 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' existing = {
  name: serverName
}

resource database 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: server
  name: name
  properties: {
    charset: charset
    collation: collation
  }
}
