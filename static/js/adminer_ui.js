// static/js/adminer_ui.js
document.addEventListener('DOMContentLoaded', function(){
  const searchBtn = document.getElementById('adminer_search_btn');
  const searchQ = document.getElementById('adminer_search_q');
  const tableName = "{{ table }}" || document.querySelector('h1')?.innerText?.trim();

  if(searchBtn){
    searchBtn.addEventListener('click', async ()=>{
      const q = searchQ.value.trim();
      if(!q){ alert('Ingresá texto para buscar'); return; }
      try {
        const res = await fetch(`/adminer/api/search?table=${encodeURIComponent(tableName)}&q=${encodeURIComponent(q)}`);
        const json = await res.json();
        if(!json.ok){ alert('Error: '+(json.error||'')); return; }
        // mostrar resultados simples: abrir nueva ventana con JSON
        const w = window.open('', '_blank');
        w.document.write('<pre>'+JSON.stringify(json.rows, null, 2)+'</pre>');
      } catch(e){
        alert('Error al buscar: '+e);
      }
    });
  }

  // Modal handlers
  const modal = document.getElementById('colEditorModal');
  const colOld = document.getElementById('col_old');
  const colNew = document.getElementById('col_new');
  const colType = document.getElementById('col_type');
  const colNull = document.getElementById('col_null');
  const colDefault = document.getElementById('col_default');
  const colBackup = document.getElementById('col_backup');
  const colApplyBtn = document.getElementById('colApplyBtn');
  const colCancelBtn = document.getElementById('colCancelBtn');
  const colMsg = document.getElementById('colEditorMsg');

  // abrir modal desde los botones "Modificar" (si usan url, cambiarlos por data-attrs; aquí hacemos delegación)
  document.body.addEventListener('click', async function(e){
    const a = e.target.closest('a');
    if(!a) return;
    if(a.href && a.href.includes('/adminer/table/') && a.href.includes('/structure/modify/')){
      e.preventDefault();
      // extraer table y col del href (fallback)
      const parts = a.getAttribute('href').split('/');
      const col = decodeURIComponent(parts[parts.length-1]);
      const table = decodeURIComponent(parts[parts.length-3]);
      // obtener meta para la columna desde servidor (reusar meta en plantilla o llamar a _get_table_meta)
      try {
        // pedimos la metadata existente recortada
        const res = await fetch(`/adminer/api/enum_values?table=${encodeURIComponent(table)}&column=${encodeURIComponent(col)}`);
        const j = await res.json();
        // rellenar campos básicos: old, new, type (obtenemos type tirando meta desde DOM -> buscamos en tabla meta)
        const row = Array.from(document.querySelectorAll('.table tr')).find(tr => tr.querySelector('td strong') && tr.querySelector('td strong').textContent.trim() === col);
        let typeText = '';
        let isNull = 'NULL';
        let def = '';
        if(row){
          // row.children: td0=columna, td1=Type, td2=Null, td3=Default...
          const td = row.querySelectorAll('td');
          if(td.length >= 4){
            typeText = td[1].textContent.trim();
            isNull = td[2].textContent.trim() === 'YES' ? 'NULL' : 'NOT NULL';
            def = td[3].textContent.trim();
            if(def === '—') def = '';
          }
        }
        colOld.value = col;
        colNew.value = col;
        colType.value = typeText;
        colNull.value = isNull;
        colDefault.value = def;
        colBackup.checked = true;
        colMsg.textContent = '';
        modal.style.display = 'flex';
      } catch(err){
        alert('No se pudo abrir editor: ' + err);
      }
    }
  });

  colCancelBtn.addEventListener('click', ()=> modal.style.display = 'none');

  colApplyBtn.addEventListener('click', async ()=>{
    colMsg.textContent = '';
    const payload = {
      table: "{{ table }}",
      old_name: colOld.value,
      new_name: colNew.value,
      col_type: colType.value,
      is_null: colNull.value,
      default: colDefault.value,
      backup: colBackup.checked
    };
    try {
      const res = await fetch('/adminer/api/alter_column', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(payload)
      });
      const j = await res.json();
      if(!j.ok){
        colMsg.textContent = 'Error: ' + (j.error || JSON.stringify(j));
        return;
      }
      colMsg.style.color = 'green';
      colMsg.textContent = 'OK — SQL ejecutado: ' + (j.sql || '');
      setTimeout(()=> location.reload(), 900);
    } catch(e){
      colMsg.textContent = 'Error conexión: ' + e;
    }
  });

});
