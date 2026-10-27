"""Three user-facing scenes; old narrow scopes remain applicability constraints."""
SCENES={'academic':'学术写作','grant':'基金写作','general':'通用'}
LEGACY={'introduction':'academic','abstract':'academic','report':'general'}

def scene(value):
    return value if value in SCENES else LEGACY.get(value,'general')

def constraints(review):
    current=scene(review.get('scope'))
    values=set(review.get('preferenceContext') or [])
    if review.get('scope') in LEGACY:values.add(review['scope'])
    return sorted(v for v in values if LEGACY.get(v)==current)

def canonical(review):
    result=dict(review)
    context=constraints(result)
    result['scope']=scene(result.get('scope'))
    if context:result['preferenceContext']=context
    else:result.pop('preferenceContext',None)
    return result

def expand_scopes(values):
    result={'general'}
    for value in values:
        result.add(value)
        if value in LEGACY:result.add(LEGACY[value])
    return result

def applicable(review):
    result={scene(review.get('scope')),*constraints(review),'general'}
    if review.get('project'):result.add('project:'+review['project'])
    return result
