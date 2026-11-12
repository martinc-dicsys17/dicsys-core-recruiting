/**
 * Form Validators & Masks - Dicsys Core
 * Validaciones client-side y máscaras de formato para formularios.
 */

// ============================================================
// MÁSCARA CUIL: XX-XXXXXXXX-X (visual), se envía como número
// ============================================================
function initCuilMask(input) {
    if (!input) return;

    input.addEventListener('input', function (e) {
        let val = this.value.replace(/\D/g, '');
        if (val.length > 11) val = val.substring(0, 11);

        let formatted = '';
        if (val.length > 0) formatted = val.substring(0, Math.min(2, val.length));
        if (val.length > 2) formatted += '-' + val.substring(2, Math.min(10, val.length));
        if (val.length > 10) formatted += '-' + val.substring(10, 11);

        this.value = formatted;
    });

    // Validar formato completo al salir del campo
    input.addEventListener('blur', function () {
        const pattern = /^\d{2}-\d{8}-\d{1}$/;
        if (this.value && !pattern.test(this.value)) {
            this.setCustomValidity('Formato CUIL inválido. Debe ser XX-XXXXXXXX-X');
            this.reportValidity();
        } else {
            this.setCustomValidity('');
        }
    });

    // Limpiar guiones solo en los parámetros del request (no tocar el input visual)
    const form = input.closest('form');
    if (form && !form._cuilCleanupAttached) {
        form.addEventListener('htmx:configRequest', function (evt) {
            if (evt.detail.parameters && evt.detail.parameters.cuil) {
                evt.detail.parameters.cuil = evt.detail.parameters.cuil.replace(/\D/g, '');
            }
        });
        form._cuilCleanupAttached = true;
    }
}

// ============================================================
// MÁSCARA DNI: XX.XXX.XXX con puntos de miles
// ============================================================
function initDniMask(input) {
    if (!input) return;

    function formatDni(digits) {
        if (!digits) return '';
        // Formatear con puntos de miles (de derecha a izquierda)
        return digits.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    }

    // Si ya tiene valor numérico, formatearlo al inicio
    if (input.value) {
        let digits = input.value.replace(/\D/g, '');
        if (digits.length > 8) digits = digits.substring(0, 8);
        input.value = formatDni(digits);
    }

    input.addEventListener('input', function () {
        let digits = this.value.replace(/\D/g, '');
        if (digits.length > 8) digits = digits.substring(0, 8);
        
        // Guardar posición del cursor
        const cursorPos = this.selectionStart;
        const prevLen = this.value.length;
        
        this.value = formatDni(digits);
        
        // Ajustar cursor después del formateo
        const diff = this.value.length - prevLen;
        this.setSelectionRange(cursorPos + diff, cursorPos + diff);
    });

    input.addEventListener('blur', function () {
        const digits = this.value.replace(/\D/g, '');
        const val = parseInt(digits, 10);
        if (digits && (isNaN(val) || val < 1000000 || val > 99999999)) {
            this.setCustomValidity('DNI debe tener entre 7 y 8 dígitos (1.000.000 - 99.999.999)');
            this.reportValidity();
        } else {
            this.setCustomValidity('');
        }
    });

    // Limpiar puntos solo en los parámetros del request (no tocar el input visual)
    const form = input.closest('form');
    if (form && !form._dniCleanupAttached) {
        form.addEventListener('htmx:configRequest', function (evt) {
            if (evt.detail.parameters && evt.detail.parameters.dni) {
                evt.detail.parameters.dni = evt.detail.parameters.dni.replace(/\D/g, '');
            }
        });
        form._dniCleanupAttached = true;
    }
}

// ============================================================
// MÁSCARA TELÉFONO: formato +XX (XXX) XXXX-XXXX
// ============================================================
function initPhoneMask(input) {
    if (!input) return;

    // Permitir escribir el "+" con el teclado (keydown no lo bloquea)
    input.addEventListener('keydown', function (e) {
        // Permitir + solo al inicio del campo
        if (e.key === '+' && this.selectionStart === 0 && !this.value.startsWith('+')) {
            return; // dejar pasar
        }
        // Bloquear + en cualquier otra posición
        if (e.key === '+' && (this.selectionStart > 0 || this.value.startsWith('+'))) {
            e.preventDefault();
        }
    });

    input.addEventListener('input', function () {
        // Quedarse solo con dígitos y el + inicial
        let raw = this.value;
        let hasPlus = raw.startsWith('+');
        let digits = raw.replace(/\D/g, '');
        if (digits.length > 15) digits = digits.substring(0, 15);

        let formatted = '';
        if (hasPlus && digits.length === 0) {
            // El usuario acaba de escribir solo el "+", dejarlo
            formatted = '+';
        } else if (hasPlus && digits.length > 0) {
            // Formato internacional: +XX (XXX) XXXX-XXXX
            let codPais = digits.substring(0, Math.min(2, digits.length));
            formatted = '+' + codPais;
            if (digits.length > 2) {
                formatted += ' (' + digits.substring(2, Math.min(5, digits.length));
                if (digits.length >= 5) formatted += ')';
            }
            if (digits.length > 5) {
                formatted += ' ' + digits.substring(5, Math.min(9, digits.length));
            }
            if (digits.length > 9) {
                formatted += '-' + digits.substring(9);
            }
        } else if (digits.length > 0) {
            // Formato local: (XXXX) XXX-XXXX
            formatted = '(' + digits.substring(0, Math.min(4, digits.length));
            if (digits.length >= 4) formatted += ')';
            if (digits.length > 4) {
                formatted += ' ' + digits.substring(4, Math.min(7, digits.length));
            }
            if (digits.length > 7) {
                formatted += '-' + digits.substring(7);
            }
        }

        this.value = formatted;
    });

    // Validar largo mínimo al salir
    input.addEventListener('blur', function () {
        let digits = this.value.replace(/\D/g, '');
        if (this.value && digits.length < 8) {
            this.setCustomValidity('El teléfono debe tener al menos 8 dígitos');
            this.reportValidity();
        } else {
            this.setCustomValidity('');
        }
    });
}

// ============================================================
// VALIDACIÓN CÓDIGO POSTAL: alfanumérico
// ============================================================
function initCodigoPostalValidation(input) {
    if (!input) return;

    input.addEventListener('input', function () {
        this.value = this.value.replace(/[^a-zA-Z0-9]/g, '').toUpperCase();
    });
}

// ============================================================
// SOLO LETRAS Y ESPACIOS (para nombre, apellido, carrera, etc.)
// ============================================================
function initTextOnly(input) {
    if (!input) return;

    input.addEventListener('input', function () {
        this.value = this.value.replace(/[^a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s\-'\.]/g, '');
    });
}

// ============================================================
// INICIALIZACIÓN GLOBAL
// ============================================================
function initFormValidators() {
    // CUIL
    initCuilMask(document.querySelector('input[name="cuil"]'));

    // DNI (máscara con puntos de miles)
    initDniMask(document.querySelector('input[name="dni"]'));

    // Teléfonos
    document.querySelectorAll('input[name="telefono_personal"], input[name="numero_emergencia"]').forEach(initPhoneMask);

    // Código Postal
    initCodigoPostalValidation(document.querySelector('input[name="codigo_postal"]'));

    // Campos de solo texto (nombre, apellido, carrera, contacto emergencia)
    document.querySelectorAll('input[name="apellido"], input[name="nombre"], input[name="carrera"], input[name="contacto_emergencia"], input[name="parentesco"]').forEach(initTextOnly);
}

// Auto-init cuando el DOM está listo
document.addEventListener('DOMContentLoaded', initFormValidators);
