#!/usr/bin/env python3
"""
Script de patch para builds customizados do RustDesk.
Aplica modificações no source do RustDesk antes do build.

Uso:
    python apply_patches.py configs/tecnico.json
    python apply_patches.py configs/go-system.json

NOTA: O script recebe o path do JSON como argumento. O diretório pai
do JSON é usado como base para resolver paths de ícones.
Ex: python apply_patches.py build-configs/build/configs/host.json
    → base_dir = build-configs/build/
"""

import json
import sys
import re
import os
import shutil
import glob

def load_config(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def read_file(filepath):
    if not os.path.exists(filepath):
        return None
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()

def write_file(filepath, content):
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

def patch_file(filepath, old, new, flags=0):
    """Substitui texto em um arquivo usando regex."""
    content = read_file(filepath)
    if content is None:
        print(f"  [AVISO] Arquivo não encontrado: {filepath}")
        return False
    new_content = re.sub(old, new, content, flags=flags)
    if new_content == content:
        print(f"  [AVISO] Nenhuma substituição feita em: {filepath}")
        return False
    write_file(filepath, new_content)
    print(f"  [OK] Patched: {filepath}")
    return True

def find_config_rs():
    """Localiza o config.rs do hbb_common."""
    candidates = [
        'libs/hbb_common/src/config.rs',
        'hbb_common/src/config.rs',
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    found = glob.glob('**/hbb_common/src/config.rs', recursive=True)
    return found[0] if found else None

# ─── SERVER CONFIG ────────────────────────────────────────────

def patch_server_config(cfg):
    """Pré-configura o servidor RustDesk no código-fonte."""
    server = cfg['server']
    api_server = cfg['api_server']
    key = cfg.get('key', '')

    config_rs = find_config_rs()
    if not config_rs:
        print("  [ERRO] config.rs não encontrado!")
        return

    content = read_file(config_rs)
    original = content

    # ── Rendezvous server ──
    # Padrão: RENDEZVOUS_SERVERS: &[&str] = &["rs-ny.rustdesk.com"];
    content = re.sub(r'"rs-[a-z]+\.rustdesk\.com"', f'"{server}"', content)

    # Padrão: env!("RENDEZVOUS_SERVER") ou option_env!
    content = re.sub(
        r'env!\("RENDEZVOUS_SERVER"\)\.to_owned\(\)',
        f'"{server}".to_owned()',
        content,
    )
    content = re.sub(
        r'option_env!\("RENDEZVOUS_SERVER"\)\s*\.unwrap_or\([^)]*\)\.to_owned\(\)',
        f'"{server}".to_owned()',
        content,
    )

    # PROD_RENDEZVOUS_SERVER — se estiver vazio, preencher
    content = re.sub(
        r'(PROD_RENDEZVOUS_SERVER\s*:\s*RwLock<String>\s*=\s*RwLock::new\()"".to_owned\(\)',
        f'\\g<1>"{server}".to_owned()',
        content,
    )

    # EXE_RENDEZVOUS_SERVER — é Default::default() (vazio). Substituir para hardcodar.
    # Linha original: pub static ref EXE_RENDEZVOUS_SERVER: RwLock<String> = Default::default();
    content = re.sub(
        r'(EXE_RENDEZVOUS_SERVER\s*:\s*RwLock<String>\s*=\s*)Default::default\(\)',
        f'\\g<1>RwLock::new("{server}".to_owned())',
        content,
    )

    # ── API server ──
    content = re.sub(r'"https?://admin\.rustdesk\.com/?[^"]*"', f'"{api_server}"', content)

    # ── Chave pública ed25519 ──
    if key:
        content = re.sub(
            r'(pub\s+const\s+RS_PUB_KEY\s*:\s*&\s*str\s*=\s*)"[^"]*"',
            f'\\g<1>"{key}"',
            content,
        )
        content = re.sub(
            r'(RENDEZVOUS_SERVER_KEY\s*=\s*)"[^"]*"',
            f'\\g<1>"{key}"',
            content,
        )

    if content != original:
        write_file(config_rs, content)
        print(f"  [OK] Server config patched: {config_rs}")
    else:
        print(f"  [AVISO] Nenhuma substituição no config.rs")

    print(f"  [INFO] Servidor: {server}")
    print(f"  [INFO] API: {api_server}")
    if key:
        print(f"  [INFO] Key: {key[:20]}...")

# ─── APP NAME ─────────────────────────────────────────────────

def patch_app_name(cfg):
    """
    Altera APP_NAME em config.rs (onde é definido) e em common.rs (comparações).
    O diagnóstico mostrou que APP_NAME é definido em hbb_common::config (config.rs)
    e apenas lido em src/common.rs.
    """
    app_name = cfg['app_name']

    # flutter/pubspec.yaml — apenas descrição
    patch_file(
        'flutter/pubspec.yaml',
        r'^description:.*$',
        f'description: {cfg.get("description", app_name)}',
        re.MULTILINE,
    )

    # ── config.rs — onde APP_NAME é DEFINIDO ──
    config_rs = find_config_rs()
    if config_rs:
        content = read_file(config_rs)
        original = content

        # Padrão: APP_NAME ... RwLock::new("RustDesk".to_owned())
        content = re.sub(
            r'(APP_NAME\b.*?RwLock::new\()"RustDesk"',
            f'\\g<1>"{app_name}"',
            content,
        )
        # Padrão alternativo sem .to_owned()
        content = re.sub(
            r'(APP_NAME\b.*?=\s*)"RustDesk"',
            f'\\g<1>"{app_name}"',
            content,
        )

        if content != original:
            write_file(config_rs, content)
            print(f"  [OK] APP_NAME patched em config.rs: {config_rs}")
        else:
            print(f"  [AVISO] APP_NAME não encontrado em config.rs — imprimindo linhas relevantes:")
            for i, line in enumerate(content.split('\n')):
                if 'APP_NAME' in line:
                    print(f"         L{i+1}: {line.strip()[:120]}")

    # ── common.rs — comparações com "RustDesk" ──
    common_rs = 'src/common.rs'
    if os.path.exists(common_rs):
        content = read_file(common_rs)
        original = content
        # Substitui comparações: .eq("RustDesk") → .eq("Host Remote")
        content = content.replace('.eq("RustDesk")', f'.eq("{app_name}")')
        if content != original:
            write_file(common_rs, content)
            print(f"  [OK] Comparações APP_NAME atualizadas em: {common_rs}")

    # NSIS installer — pode não existir em todas as versões
    for nsis_file in ['res/setup.nsi', 'res/msi/main.wxs']:
        if os.path.exists(nsis_file):
            patch_file(nsis_file, r'RustDesk', app_name)

    print(f"  [INFO] Nome do app: {app_name}")

# ─── ÍCONES ───────────────────────────────────────────────────

def copy_icons(cfg, base_dir):
    """
    Substitui ícones. Os paths no JSON são relativos ao diretório build/,
    que está em base_dir (ex: build-configs/build/).
    """
    icons = cfg.get('icons', {})
    icon_map = {
        'windows': 'res/app.ico',
        'flutter': 'flutter/assets/icon.png',
    }
    for key, src_rel in icons.items():
        dst = icon_map.get(key)
        if not dst:
            continue
        # Tenta path relativo ao base_dir (build-configs/build/icons/host.ico)
        src = os.path.join(base_dir, src_rel)
        if not os.path.exists(src):
            # Tenta path direto
            src = src_rel
        if os.path.exists(src):
            shutil.copy2(src, dst)
            print(f"  [OK] Ícone copiado: {src} → {dst}")
        else:
            print(f"  [AVISO] Ícone não encontrado: {src_rel} (tentou: {os.path.join(base_dir, src_rel)})")

# ─── UI CLIENTE ────────────────────────────────────────────────

def apply_simple_client_page(cfg):
    """
    Aplica patches no desktop_home_page.dart para simplificar a UI cliente.
    Remove o painel direito (ConnectionPage) mantendo apenas o painel esquerdo
    (ID + senha).
    """
    target_path = 'flutter/lib/desktop/pages/desktop_home_page.dart'
    if not os.path.exists(target_path):
        print(f"  [AVISO] desktop_home_page.dart não encontrado")
        return

    content = read_file(target_path)
    original = content

    # ── Patch 1: Remover o painel direito (ConnectionPage) ──
    # Original: Row com buildLeftPane + VerticalDivider + ConnectionPage()
    # O build() tem este bloco:
    #   children: [
    #     buildLeftPane(context),
    #     if (!isIncomingOnly) const VerticalDivider(width: 1),
    #     if (!isIncomingOnly) Expanded(child: buildRightPane(context)),
    #   ],
    # Vamos forçar isIncomingOnly = true efetivamente removendo o painel direito
    content = content.replace(
        'if (!isIncomingOnly) const VerticalDivider(width: 1),',
        '// Removido: painel de conexão (versão cliente)',
    )
    content = content.replace(
        'if (!isIncomingOnly) Expanded(child: buildRightPane(context)),',
        '// Removido: ConnectionPage (versão cliente)',
    )

    # ── Patch 2: Forçar largura fixa no leftPane ──
    # O buildLeftPane retorna um Container com largura fixa (normalmente ~246)
    # Vamos expandir para ocupar toda a janela
    content = content.replace(
        'buildLeftPane(context),',
        'Expanded(child: buildLeftPane(context)),',
    )

    if content != original:
        write_file(target_path, content)
        print(f"  [OK] UI simplificada: removido painel direito (ConnectionPage)")
    else:
        print(f"  [AVISO] Patches de UI não casaram — imprimindo build():")
        for i, line in enumerate(content.split('\n')):
            if any(kw in line for kw in ['buildLeftPane', 'buildRightPane', 'ConnectionPage', 'VerticalDivider', 'isIncomingOnly']):
                print(f"         L{i+1}: {line.strip()[:120]}")

def lock_network_settings(cfg):
    """Bloqueia aba Rede nas configurações (versão cliente)."""
    setting_page = 'flutter/lib/desktop/pages/desktop_setting_page.dart'
    patch_file(
        setting_page,
        r"(case\s+'network'\s*:)",
        r"// Bloqueado na versão cliente\n        return Container();\n        // \1",
    )

# ─── PORTABLE PACKER (INSTALADOR) ─────────────────────────────

def patch_portable_packer(cfg):
    """
    Patcheia o portable packer (libs/portable) para usar o nome customizado.
    O packer é o exe auto-extraível que funciona como instalador.
    """
    app_name = cfg['app_name']
    # APP_PREFIX deve ser idêntico ao APP_NAME para que is_setup_portable() no
    # app principal reconheça %LOCALAPPDATA%\{APP_PREFIX}\Data\ como extração do packer.
    # Kebab-case causava mismatch: packer extraía para "go-system-remote\" mas o app
    # esperava "Go System Remote\" → portable detection falhava, TOMLs não eram lidos.
    app_prefix = app_name

    # ── main.rs — APP_PREFIX (diretório de extração) ──
    main_rs = 'libs/portable/src/main.rs'
    if os.path.exists(main_rs):
        content = read_file(main_rs)
        original = content
        content = content.replace(
            'const APP_PREFIX: &str = "rustdesk"',
            f'const APP_PREFIX: &str = "{app_prefix}"',
        )
        if content != original:
            write_file(main_rs, content)
            print(f"  [OK] APP_PREFIX patched: {app_prefix}")
        else:
            print(f"  [AVISO] APP_PREFIX não encontrado em {main_rs}")

    # ── Cargo.toml — metadados do exe (winres) ──
    cargo_toml = 'libs/portable/Cargo.toml'
    if os.path.exists(cargo_toml):
        content = read_file(cargo_toml)
        original = content
        content = re.sub(
            r'(ProductName\s*=\s*)"[^"]*"',
            f'\\g<1>"{app_name}"',
            content,
        )
        content = re.sub(
            r'(FileDescription\s*=\s*)"[^"]*"',
            f'\\g<1>"{cfg.get("description", app_name)}"',
            content,
        )
        if content != original:
            write_file(cargo_toml, content)
            print(f"  [OK] Portable packer Cargo.toml patched")

    print(f"  [INFO] Portable packer prefix: {app_prefix}")


# ─── DESABILITAR UPDATE CHECK ─────────────────────────────────

def disable_update_check():
    """
    Remove a verificação de atualização do RustDesk.
    O banner 'versão menor' aparece porque compara com rustdesk.com.
    Como usamos nosso próprio servidor, essa verificação não faz sentido.
    """
    # Método 1: Limpar a URL de update no desktop_home_page.dart
    # O buildHelpCards recebe updateUrl — se for vazio, não mostra nada
    home_page = 'flutter/lib/desktop/pages/desktop_home_page.dart'
    if os.path.exists(home_page):
        content = read_file(home_page)
        original = content
        # Substituir a chamada que passa updateUrl para buildHelpCards
        # Forçar string vazia para nunca mostrar o card de update
        content = content.replace(
            'buildHelpCards(stateGlobal.updateUrl.value)',
            'buildHelpCards("")',
        )
        if content != original:
            write_file(home_page, content)
            print(f"  [OK] Update check desabilitado em desktop_home_page.dart")
        else:
            print(f"  [AVISO] Padrão buildHelpCards não encontrado — tentando alternativa")
            # Alternativa: procurar por updateUrl genérico
            content = re.sub(
                r'buildHelpCards\([^)]*updateUrl[^)]*\)',
                'buildHelpCards("")',
                content,
            )
            if content != original:
                write_file(home_page, content)
                print(f"  [OK] Update check desabilitado (alternativa)")

    # Método 2: Desabilitar a verificação no Rust (common.rs ou similar)
    # Procura a URL de update e limpa
    for rs_file in glob.glob('src/**/*.rs', recursive=True):
        content = read_file(rs_file)
        if content and 'releases' in content and 'rustdesk.com' in content:
            original = content
            content = re.sub(r'"https?://[^"]*rustdesk\.com[^"]*releases[^"]*"', '""', content)
            if content != original:
                write_file(rs_file, content)
                print(f"  [OK] URL de releases limpa em: {rs_file}")

    # Método 3: Desabilitar no consts.dart
    consts_dart = 'flutter/lib/consts.dart'
    if os.path.exists(consts_dart):
        content = read_file(consts_dart)
        original = content
        content = re.sub(r"(updateUrl\s*=\s*)'[^']*'", r"\g<1>''", content)
        content = re.sub(r'(updateUrl\s*=\s*)"[^"]*"', r'\g<1>""', content)
        if content != original:
            write_file(consts_dart, content)
            print(f"  [OK] updateUrl limpa em consts.dart")

# ─── DIAGNÓSTICO ──────────────────────────────────────────────

def print_diagnostics():
    """Imprime informações de diagnóstico sobre o source."""
    config_rs = find_config_rs()
    if config_rs:
        content = read_file(config_rs)
        for pattern, label in [
            (r'RENDEZVOUS_SERVER', 'RENDEZVOUS_SERVER'),
            (r'RS_PUB_KEY', 'RS_PUB_KEY'),
            (r'admin\.rustdesk\.com', 'admin.rustdesk.com'),
            (r'APP_NAME', 'APP_NAME (config.rs)'),
        ]:
            matches = re.findall(f'.*{pattern}.*', content)
            if matches:
                print(f"  [DIAG] {label}: {len(matches)}x em {config_rs}")
                for m in matches[:3]:
                    print(f"         {m.strip()[:120]}")

    common_rs = 'src/common.rs'
    if os.path.exists(common_rs):
        content = read_file(common_rs)
        matches = re.findall(r'.*APP_NAME.*', content)
        if matches:
            print(f"  [DIAG] APP_NAME (common.rs): {len(matches)}x")
            for m in matches[:3]:
                print(f"         {m.strip()[:120]}")

# ─── MAIN ─────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Uso: python apply_patches.py <config.json>")
        sys.exit(1)

    config_path = sys.argv[1]
    # base_dir = diretório do build (ex: build-configs/build/) para resolver ícones
    # config_path é algo como: build-configs/build/configs/host.json
    # → configs/ está dentro de build/, então subimos 1 nível
    config_dir = os.path.dirname(config_path)  # build-configs/build/configs
    base_dir = os.path.dirname(config_dir)       # build-configs/build

    print(f"\n=== Aplicando patches: {config_path} ===")
    print(f"  Base dir para ícones: {base_dir}\n")
    cfg = load_config(config_path)

    print("[0/6] Diagnóstico do source...")
    print_diagnostics()

    print("\n[1/6] Configurando servidor...")
    patch_server_config(cfg)

    print("\n[2/6] Configurando nome do app...")
    patch_app_name(cfg)

    print("\n[3/6] Copiando ícones...")
    copy_icons(cfg, base_dir)

    print("\n[4/6] Desabilitando update check...")
    disable_update_check()

    print("\n[5/6] Configurando portable packer (instalador)...")
    patch_portable_packer(cfg)

    # Senha permanente é configurada via TOML no workflow (data/{AppName}.toml)

    build_type = cfg.get('type', 'technician')
    if build_type == 'client':
        print("\n[6/6] Aplicando UI simplificada (modo cliente)...")
        apply_simple_client_page(cfg)
        lock_network_settings(cfg)
    else:
        print("\n[6/6] Versão técnico — UI completa mantida.")

    print(f"\n=== Patches aplicados com sucesso! Build: {cfg['app_name']} ===\n")

if __name__ == '__main__':
    main()
