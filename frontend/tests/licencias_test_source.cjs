const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function cargarScript(nombre, contexto) {
  const templatePath = path.resolve(__dirname, '../modulos/innovacion/templates/innovacion', nombre);
  const template = fs.readFileSync(templatePath, 'utf8');
  const aperturas = template.match(/<script\b[^>]*>/g) || [];
  const cierres = template.match(/<\/script>/g) || [];
  if (aperturas.length !== 1 || cierres.length !== 1) {
    throw new Error(`Expected exactly one script in ${templatePath}`);
  }
  const inicio = template.indexOf(aperturas[0]) + aperturas[0].length;
  const script = template.slice(inicio, template.lastIndexOf('</script>'))
    .replace(/{{[\s\S]*?}}/g, 'null');
  vm.runInContext(script, contexto, { filename: templatePath });
}

module.exports = { cargarScript };
