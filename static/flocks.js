window.tweak_content=function() {
    var anchor=location.hash;
    if (anchor) {
        $(anchor).addClass('hilite').focus();
    }
    $('a:not(.internal-link)').attr('target','_blank');
}
$(function() {
    $.manageAjax.create('flocks'); 
    window.tweak_content();
});

window.populate_from_feed=function(ul,data) {
    for (e in data['entries']) { 
        entry=data['entries'][e];
        feed_dir=entry['feed_rtl']?'rtl':'ltr';
        var span=$('<span/>').addClass('toggler-label');
        span.append($('<div/>').addClass('item-time').text(entry['friendly_time']));
        span.append($('<a/>').addClass('internal-link feed-reference').attr(
            'href',window.HTML_FEED_URL+'?url='+entry['feed_url']).text(entry['feed_title']));
        span.append(': ').append($('<a/>').addClass('entry_title').addClass(feed_dir).attr(
            'href',entry['link']).html(entry['title']));
        var li=$('<li/>').attr('id',entry['id']).append(
            span).append($('<input/>').addClass('toggler').attr('type','checkbox'));
        li.append($('<div/>').addClass('entry-description').addClass(feed_dir).html(entry['description']));
        li.data('modified',entry['modified']);
        var sameold=ul.find('#'+li.attr('id'));
        if (sameold.length) {
            sameold.eq(0).replaceWith(li);
        } else {
            var older=ul.find('li').filter(function() {
                return $(this).data('modified')<li.data('modified');
            });
            if (older.length) {
               	older.eq(0).before(li); 
            } else {
                ul.append(li);
            }
        }
    }
}

window.fetch_from_feed=function(ul_id,feed_title,feed_url) {
    var ul=$('#'+ul_id);
    var loading=$('<li/>').html(AJAX_LOADER_HTML).prepend('Loading '+feed_title+': ');
    ul.prepend(loading);
    $.manageAjax.add('flocks',{
        url:window.AJAX_FEED_URL,
        data:{url:feed_url},
        ul:ul,
        loading:loading,
        success:function(data,textStatus,xhr,options){
            options['loading'].remove();
            populate_from_feed(options['ul'],data);
            window.tweak_content();
        },
        error:function(data,textStatus,xhr,options){
            options['loading'].find('img').replaceWith('failed');
        },
        abort:function(data,textStatus,xhr,options){
            options['loading'].find('img').replaceWith('aborted');
        }
    });
}

