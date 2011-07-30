# -*- coding: utf-8 -*-
from django.template import RequestContext
from django.shortcuts import render_to_response
from django.http import HttpResponse, HttpResponseRedirect
from django.db.models import get_model, Sum, Q
from django.utils import simplejson

#importaciones de los models
from forms import ConsultarForm
from trocaire.medios.templatetags.tools import *
from trocaire.medios.models import *
from trocaire.familia.models import *
from trocaire.participacion_ciudadana.models import *
from trocaire.crisis_alimentaria.models import *
from trocaire.lugar.models import *
from trocaire.ingresos.models import *
from trocaire.produccion.models import *
import copy

def _query_set_filtrado(request):
    #anio = int(request.session['fecha'])
    params = {}
    #if 'fecha' in request.session:
    #    params['fecha__year'] = anio
        
    if 'contraparte' in request.session:
        params['contraparte'] =  request.session['contraparte'] 

        if 'departamento' in request.session:
            if 'municipio' in request.session:
                if 'comarca' in request.session:
                    params['comarca'] = request.session['comarca']
                else:
                    params['comarca__municipio'] = request.session['municipio']
            else:
                params['comarca__municipio__departamento'] = request.session['departamento']
            
        unvalid_keys = []
        for key in params:
            if not params[key]:
                unvalid_keys.append(key)
        
        for key in unvalid_keys:
            del params[key]
        #despelote
        encuestas_id = []
        reducir = False
        last_key = (None, None)
        for i, key in enumerate(request.session['parametros']):
            #TODO: REVISAR ESTO
            for k, v in request.session['parametros'][key].items():
                if v is None or str(v) == 'None':
                    del request.session['parametros'][key][k]
            model = get_model(*key.split('.'))
            if len(request.session['parametros'][key]):
                reducir = True if (last_key[1] != key > 1 and last_key[0] == None) or reducir==True else False
                last_key = (i, key)
                ids = model.objects.filter(**request.session['parametros'][key]).values_list('id', flat=True)
                encuestas_id += ids
        if not encuestas_id:
            return Encuesta.objects.filter(**params)
        else:
            ids_definitivos = reducir_lista(encuestas_id) if reducir else encuestas_id
            return Encuesta.objects.filter(id__in = ids_definitivos, **params)

#===============================================================================
def consultar(request):
    if request.method == 'POST':
        form = ConsultarForm(request.POST)
        if form.is_valid():
            #request.session['fecha'] = form.cleaned_data['fecha']
            request.session['departamento'] = form.cleaned_data['departamento']
            request.session['contraparte'] = form.cleaned_data['contraparte']
            try:
                municipio = Municipio.objects.get(id=form.cleaned_data['municipio']) 
            except:
                municipio = None
            try:
                comarca = Comarca.objects.get(id=form.cleaned_data['comarca'])
            except:
                comarca = None

            request.session['municipio'] = municipio
            request.session['comarca'] = comarca

            #cosas de otros modelos!
            parametros = {'familia.escolaridad': {}, 'familia.composicion': {}, 
                          'genero.tomadecicion': {}, 'ingresos.principalesfuentes': {},
                          'ingresos.totalingreso': {}}
            parametros['familia.escolaridad']['beneficia'] = form.cleaned_data['escolaridad_beneficiario']
            parametros['familia.escolaridad']['conyugue'] = form.cleaned_data['escolaridad_conyugue']
            parametros['familia.composicion']['sexo'] = form.cleaned_data['familia_beneficiario']
            #desicion gasto mayor!
            #parametros['genero.tomadecicion']['aspectos'] = 1
            parametros['genero.tomadecicion']['respuesta'] =  form.cleaned_data['desicion_gasto_mayor']
            #ingresos
            parametros['ingresos.principalesfuentes']['fuente'] = form.cleaned_data['ingresos_fuente']#TODO: cambiarlo a fuente__in
            parametros['ingresos.totalingreso']['total__gte'] = form.cleaned_data['ingresos_total_min']
            parametros['ingresos.totalingreso']['total__lte'] = form.cleaned_data['ingresos_total_max']
            #dependientes
            parametros['familia.composicion']['dependientes__gte'] = form.cleaned_data['dependientes_min']
            parametros['familia.composicion']['dependientes__lte'] = form.cleaned_data['dependientes_max']
            #parametros['formas_propiedad.finca']['area'] = forms.cleaned_data['finca_area_total']
            #parametros['produccion.ganadomayor']['num_vacas'] = forms.cleaned_data['finca_num_vacas']
            #parametros['finca']['conssa'] = forms.cleaned_data['finca_conssa']
            #parametros['finca']['num_productos'] = forms.cleaned_data['finca_num']
            request.session['parametros'] = parametros

            if form.cleaned_data['next_url']:
                return HttpResponseRedirect(form.cleaned_data['next_url'])
            else:
                muestra_indicador =1
                return render_to_response('encuestas/consultar.html', locals(),
                              context_instance=RequestContext(request))
    else:
        form = ConsultarForm()
    return render_to_response('encuestas/consultar.html', locals(),
                              context_instance=RequestContext(request))

#===============================================================================

def index(request, template_name="index.html"):
    return render_to_response(template_name, locals(),
                              context_instance=RequestContext(request))

#FUNCIONES UTILITARIAS PARA TODO EL SITIO 
def get_municipios(request, departamento):
    municipios = Municipio.objects.filter(departamento = departamento)
    lista = [(municipio.id, municipio.nombre) for municipio in municipios]
    return HttpResponse(simplejson.dumps(lista), mimetype='application/javascript')
        
def get_comarca(request, municipio):
    comarcas = Comarca.objects.filter(municipio = municipio)
    lista = [(comarca.id, comarca.nombre) for comarca in comarcas]
    return HttpResponse(simplejson.dumps(lista), mimetype='application/javascript')

def indicadores(request):
    return render_to_response('encuestas/indicadores.html',
                              context_instance=RequestContext(request))
    
#========================= Salidas sencillas ==================================
def datos_sexo(request):    
    encuestas = _query_set_filtrado(request).values_list('id', flat=True)    
    composicion_familia = Composicion.objects.filter(encuesta__id__in=encuestas)
    '''1: Hombre, 2: Mujer, 3: Compartido'''    
    tabla_sexo_jefe = {1: 0, 2: 0, 3: 0}
    tabla_sexo_beneficiario = {}
    for composicion in composicion_familia:
        #validar si el beneficiario es el jefe de familia
        if composicion.beneficio == 1:
            tabla_sexo_jefe[composicion.sexo] += 1
        elif composicion.beneficio == 2:
            tabla_sexo_jefe[composicion.sexo_jefe] += 1            
        else:
            tabla_sexo_jefe[3] += 1
    tabla_sexo_beneficiario['masculino'] = composicion_familia.filter(sexo=1).count()
    tabla_sexo_beneficiario['femenino'] = composicion_familia.filter(sexo=2).count()                
        
    return render_to_response('encuestas/datos_sexo.html', RequestContext(request, locals()))

def sexo_beneficiario(request):
    encuestas = _query_set_filtrado(request).values_list('id', flat=True)
    composicion_familia = Composicion.objects.filter(encuesta__id__in=encuestas)
    '''1: hombre, 2: mujer'''
    mujer_jefe = {1:0, 2:0}
    hombre_jefe = {1:0, 2:0}
    
    for composicion in composicion_familia:
        #validando si el beneficiario es el jefe y es hombre
        if composicion.beneficio == 1 and composicion.sexo == 1:            
            hombre_jefe[1] += 1
        #si el beneficiario es jefe y es mujer
        elif composicion.beneficio == 1 and composicion.sexo == 2:
            mujer_jefe[2] += 1
        #si el beneficiario no es el jefe, buscar su sexo
        elif composicion.beneficio == 2:
            if composicion.sexo_jefe == 1:
                hombre_jefe[composicion.sexo] += 1
            elif composicion.sexo_jefe == 2:
                mujer_jefe[composicion.sexo] += 1                        
    
    return render_to_response('encuestas/sexo_beneficiario.html', RequestContext(request, locals()))

def escolaridad(request):    
    encuestas = _query_set_filtrado(request)
    esc_benef = {}
    #escolaridad por hombre y mujer
    esc_h_m = {}
    for nivel_edu in CHOICE_ESCOLARIDAD:
        escolaridad_query = Escolaridad.objects.filter(beneficia=nivel_edu[0], encuesta__in=encuestas)
        esc_benef[nivel_edu[1]] = escolaridad_query.count()
        esc_h_m[nivel_edu[1]] = _hombre_mujer_dicc(escolaridad_query.values_list('encuesta__id', flat=True))        
    tabla_esc_benef = _order_dicc(copy.deepcopy(esc_benef))
    
    return render_to_response('encuestas/escolaridad.html', RequestContext(request, locals()))

def credito(request):
    encuestas = _query_set_filtrado(request)
    opciones = Credito.objects.all()
    credito = {}
    credito_h_m = {}
    for op in opciones:
        query = AccesoCredito.objects.filter(Q(hombre=op) | Q(mujer=op) | Q(otro_hombre=op) | Q(otra_mujer=op),
                                                                encuesta__in=encuestas)
        credito[op.nombre] = query.count()
        credito_h_m[op.nombre] = _hombre_mujer_dicc(query.values_list('encuesta__id', flat=True), jefe=True)
    tabla_credito = _order_dicc(copy.deepcopy(credito))
            
    return render_to_response('encuestas/credito.html', RequestContext(request, locals()))

def participacion(request):
    encuestas = _query_set_filtrado(request)
    part_cpc = {}
    part_asam = {}    
    query1 = ParticipacionCPC.objects.filter(encuesta__in=encuestas, organismo=1)
    part_cpc = query1.aggregate(hombres=Sum('hombre'), mujer=Sum('mujer'), ambos=Sum('ambos'))    
    
    query2 = ParticipacionCPC.objects.filter(encuesta__in=encuestas, organismo=2)
    part_asam = query2.aggregate(hombres=Sum('hombre'), mujer=Sum('mujer'), ambos=Sum('ambos'))
    return render_to_response('encuestas/participacion.html', RequestContext(request, locals()))

def ingreso_agropecuario(request):
    encuestas = _query_set_filtrado(request)
    query = PrincipalesFuentes.objects.filter(encuesta__in=encuestas)
    jefe_ids = _queryid_hombre_mujer(encuestas.values_list('id', flat=True))
    
    #obtener queries segun jefe de familia
    query_hombre = PrincipalesFuentes.objects.filter(encuesta__id__in=jefe_ids[1])
    query_mujer = PrincipalesFuentes.objects.filter(encuesta__id__in=jefe_ids[2])    
    query_compartido = PrincipalesFuentes.objects.filter(encuesta__id__in=jefe_ids[3])
            
    ingreso_agropecuario = {'total': calcular_frecuencia(query.filter(fuentes_ap__gte=1).count(), query.count()),
            'hombre': calcular_frecuencia(query_hombre.filter(fuentes_ap__gte=1).count(), query_hombre.count()), 
            'mujer': calcular_frecuencia(query_mujer.filter(fuentes_ap__gte=1).count(), query_mujer.count()),
            'compartido': calcular_frecuencia(query_compartido.filter(fuentes_ap__gte=1).count(), query_compartido.count()),}
    return render_to_response('encuestas/ingreso_agropecuario.html', RequestContext(request, locals()))

def ingreso_familiar(request):
    encuestas = _query_set_filtrado(request)
    ingresos = TotalIngreso.objects.filter(encuesta__in=encuestas).values_list('total', flat=True)
    jefe_ids = _queryid_hombre_mujer(encuestas.values_list('id', flat=True))
    
    #obtener queries segun jefe de familia
    query_hombre_jefe = TotalIngreso.objects.filter(encuesta__id__in=jefe_ids[1]).values_list('total', flat=True)
    query_mujer_jefe = TotalIngreso.objects.filter(encuesta__id__in=jefe_ids[2]).values_list('total', flat=True)    
    query_compartido_jefe = TotalIngreso.objects.filter(encuesta__id__in=jefe_ids[3]).values_list('total', flat=True)
    
    promedio = {'total': calcular_promedio(ingresos),
                'hombre_jefe': calcular_promedio(query_hombre_jefe),
                'mujer_jefe': calcular_promedio(query_mujer_jefe),
                'compartido': calcular_promedio(query_compartido_jefe)
                }
    
    mediana = {'total': calcular_mediana(ingresos),
                'hombre_jefe': calcular_mediana(query_hombre_jefe),
                'mujer_jefe': calcular_mediana(query_mujer_jefe),
                'compartido': calcular_mediana(query_compartido_jefe)
                }
    
    return render_to_response('encuestas/ingreso_familiar.html', RequestContext(request, locals()))

def abastecimiento(request):
    encuestas = _query_set_filtrado(request)
    jefes_ids = _queryid_hombre_mujer(encuestas.values_list('id', flat=True), flag=True)     
    frijol = {1: 0, 2: 0, 3: 0}
    maiz = {1: 0, 2: 0, 3: 0}
    
    encuestas_sin_consumo = []
    encuestas_sin_maiz = []
    encuestas_sin_frijol = []
    
    for key, lista in jefes_ids.items():
        for encuesta in lista:
            #total_personas = sum([desc.femenino+desc.masculino for desc in Descripcion.objects.filter(encuesta=encuesta)])
            try:
                consumo_query = ConsumoDiario.objects.get(encuesta=encuesta)
                maiz_query = CultivosPeriodos.objects.get(encuesta=encuesta, cultivos__id=1)                
            except ConsumoDiario.DoesNotExist:
                encuestas_sin_consumo.append(encuesta.id)
                jefes_ids[key].remove(encuesta)              
                continue
            except CultivosPeriodos.DoesNotExist:
                encuestas_sin_maiz.append(encuesta.id)   
                jefes_ids[key].remove(encuesta)             
                continue
            except:                
                continue
                
            try:
                frijol_query = CultivosPeriodos.objects.get(encuesta=encuesta, cultivos__id=3)                
            except CultivosPeriodos.DoesNotExist:
                encuestas_sin_frijol.append(encuesta.id)
                jefes_ids[key].remove(encuesta)
                continue
            
            produccion_diaria_maiz = round((maiz_query.produccion*float(100))/float(365), 2)
            produccion_diaria_frijol = round((frijol_query.produccion*float(100))/float(365), 2)
            if consumo_query.maiz <= produccion_diaria_maiz:
                maiz[key] += 1
        
            if consumo_query.frijol <= produccion_diaria_frijol:
                frijol[key] += 1
                
    frijol['total'] = sum(frijol.values())
    maiz['total'] = sum(maiz.values())
    
    totales = {1: len(jefes_ids[1]), 2: len(jefes_ids[2]), 3: len(jefes_ids[3])}
    totales['total'] = sum(totales.values())
            
    return render_to_response('encuestas/abastecimiento.html', RequestContext(request, locals()))

def reducir_lista(lista):
    '''reduce la lista dejando solo los elementos que son repetidos
       osea lo contraron a unique'''
    nueva_lista = []
    for foo in lista:
        if lista.count(foo) > 1 and foo not in nueva_lista:
            nueva_lista.append(foo)
    return nueva_lista

def _hombre_mujer_dicc(ids, jefe=False):
    '''Funcion que por defecto retorna la cantidad de beneficiarios
    hombres y mujeres de una lista de ids. Si jefe=True, retorna los
    jefes de familia hombres y mujeres segun la lista de ids :D'''
    composicion_familia = Composicion.objects.filter(encuesta__id__in=ids)
    if jefe:
        '''1: Hombre, 2: Mujer, 3: Compartido'''    
        dicc = {1: 0, 2: 0, 3: 0}    
        for composicion in composicion_familia:
            #validar si el beneficiario es el jefe de familia
            if composicion.beneficio == 1:
                dicc[composicion.sexo] += 1
            elif composicion.beneficio == 2:
                dicc[composicion.sexo_jefe] += 1     
            else:
                dicc[3] += 1
            
        return dicc
                       
    return {
            'hombre': composicion_familia.filter(sexo=1).count(),
            'mujer': composicion_familia.filter(sexo=2).count()
            }

def _queryid_hombre_mujer(ids, flag=False):
    '''funcion que retorna las encuestas separadas por tipo de jefe,
    Hombre, Mujer y Compartido'''
    composicion_familia = Composicion.objects.filter(encuesta__id__in=ids)
    
    '''1: Hombre, 2: Mujer, 3: Compartido'''    
    dicc = {1: [], 2: [], 3: []}
    for composicion in composicion_familia:
        #validar si el beneficiario es el jefe de familia
        if composicion.beneficio == 1:
            if not flag:
                dicc[composicion.sexo].append(composicion.encuesta.id)
            else:
                dicc[composicion.sexo].append(composicion.encuesta)
        elif composicion.beneficio == 2:
            if not flag:
                dicc[composicion.sexo_jefe].append(composicion.encuesta.id)
            else:
                dicc[composicion.sexo_jefe].append(composicion.encuesta)                          
        else:
            if not flag:
                dicc[3].append(composicion.encuesta.id)
            else:
                dicc[3].append(composicion.encuesta)
            
    return dicc                    
     
def _order_dicc(dicc):
    return sorted(dicc.items(), key=lambda x: x[1], reverse=True)

def calcular_promedio(lista):
    n = len(lista)
    total_suma = sum(lista)
    
    return round(total_suma/n, 2) 

def calcular_mediana(lista):
    n = len(lista)
    lista = sorted(lista)
    
    #calcular si lista es odd or even
    if (n%2) == 1:
        index = (n+1)/2
        return lista[index-1]
    else:
        index_1 = (n/2)
        index_2 = index_1+1
        return calcular_promedio([lista[index_1-1], lista[index_2-1]])
    

